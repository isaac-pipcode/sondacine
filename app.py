import streamlit as st
import pandas as pd
import pypdf
import re
import plotly.express as px
from io import BytesIO

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="CineData BR - Analítica ANCINE",
    page_icon="🎬",
    layout="wide"
)

# --- FUNÇÕES DE LIMPEZA E EXTRAÇÃO (ENGINE) ---

def clean_currency_br(x):
    """Converte string '1.000,00' para float 1000.00"""
    if not isinstance(x, str):
        return 0.0
    clean = x.replace('R$', '').strip()
    clean = clean.replace('.', '') # Remove milhar
    clean = clean.replace(',', '.') # Troca decimal
    try:
        return float(clean)
    except ValueError:
        return 0.0

def clean_int_br(x):
    """Converte string '1.000' para int 1000"""
    if not isinstance(x, str):
        return 0
    clean = x.replace('.', '').strip()
    try:
        return int(clean)
    except ValueError:
        return 0

@st.cache_data(show_spinner=False)
def parse_ancine_pdf(uploaded_files):
    """Lê múltiplos PDFs da ANCINE e extrai dados tabulares via Regex."""
    data = []
    
    # Regex para identificar CPB (ex: B0901024500000 ou E1402431200000)
    # O CPB é o divisor mais seguro entre o Título e os metadados
    cpb_pattern = re.compile(r'([BE]\d{13})')
    
    # Regex para garantir que a linha começa com um Ano (4 dígitos)
    year_check = re.compile(r'^(\d{4})\s+')

    for uploaded_file in uploaded_files:
        try:
            reader = pypdf.PdfReader(uploaded_file)
            
            for page in reader.pages:
                text = page.extract_text()
                if not text: continue
                
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    
                    # Filtro 1: A linha deve começar com um ano
                    if not year_check.match(line):
                        continue
                    
                    # Divisão: Título [CPB] Metadados
                    parts = cpb_pattern.split(line)
                    
                    if len(parts) >= 3:
                        # parts[0] -> "2009 Título do Filme "
                        # parts[1] -> "B090000..." (O CPB)
                        # parts[2] -> " Ficção ... 10.000 50.000,00"
                        
                        header_part = parts[0].strip()
                        meta_part = parts[-1].strip()
                        
                        # Extrair Ano e Título da primeira parte
                        try:
                            ano = header_part[:4]
                            titulo = header_part[4:].strip()
                        except:
                            continue # Falha na estrutura
                        
                        # Extrair Público e Renda da última parte (últimos 2 tokens)
                        tokens = meta_part.split()
                        if len(tokens) >= 2:
                            renda_raw = tokens[-1]
                            publico_raw = tokens[-2]
                            
                            # Identificar Nacionalidade (heuristicamente)
                            nacionalidade = "Brasileira" if "Brasileira" in meta_part else "Estrangeira"
                            
                            data.append({
                                'Ano_Exibicao': int(ano),
                                'Titulo': titulo,
                                'Nacionalidade': nacionalidade,
                                'Publico': clean_int_br(publico_raw),
                                'Renda': clean_currency_br(renda_raw)
                            })
                            
        except Exception as e:
            st.error(f"Erro ao ler arquivo {uploaded_file.name}: {e}")

    return pd.DataFrame(data)

# --- INTERFACE (FRONTEND) ---

st.title("🎬 CineData BR: Mineração de Dados da ANCINE")
st.markdown("""
Esta ferramenta processa os arquivos PDF de **"Listagem de Filmes Exibidos"** da ANCINE, 
estrutura os dados e gera visualizações para pesquisa acadêmica.
""")

# Sidebar
with st.sidebar:
    st.header("1. Ingestão de Dados")
    uploaded_files = st.file_uploader(
        "Arraste os PDFs da ANCINE aqui", 
        type="pdf", 
        accept_multiple_files=True
    )
    
    process_btn = st.button("Processar Arquivos", type="primary")
    
    st.info("Nota: O processamento usa Regex para limpar a formatação inconsistente dos PDFs originais.")

# Lógica Principal
if process_btn and uploaded_files:
    with st.spinner("Lendo PDFs, limpando dados e estruturando tabelas..."):
        df_raw = parse_ancine_pdf(uploaded_files)
        
    if not df_raw.empty:
        st.success(f"Sucesso! {len(df_raw)} registros de exibição processados.")
        
        # Agrupamento (Somar bilheterias de anos diferentes para o mesmo filme)
        # Normalizamos o título para evitar duplicatas por caixa alta/baixa
        df_raw['Titulo_Norm'] = df_raw['Titulo'].str.upper().str.strip()
        
        df_grouped = df_raw.groupby(['Titulo_Norm', 'Nacionalidade']).agg({
            'Titulo': 'first',
            'Publico': 'sum',
            'Renda': 'sum',
            'Ano_Exibicao': 'min' # Ano de Lançamento (ou primeira aparição)
        }).reset_index()
        
        # --- ABAS DE ANÁLISE ---
        tab1, tab2, tab3 = st.tabs(["📊 Tabelas & Rankings", "📈 Visualização Gráfica", "🔍 Diagnóstico"])
        
        with tab1:
            st.subheader("Filtros de Pesquisa")
            col1, col2 = st.columns(2)
            
            with col1:
                years = st.slider(
                    "Selecione o Período", 
                    min_value=int(df_grouped['Ano_Exibicao'].min()),
                    max_value=int(df_grouped['Ano_Exibicao'].max()),
                    value=(2010, 2023)
                )
            with col2:
                only_br = st.checkbox("Apenas Filmes Brasileiros", value=True)
            
            # Aplicação dos Filtros
            mask = (df_grouped['Ano_Exibicao'] >= years[0]) & (df_grouped['Ano_Exibicao'] <= years[1])
            if only_br:
                mask = mask & (df_grouped['Nacionalidade'] == 'Brasileira')
            
            df_filtered = df_grouped[mask]
            
            col_a, col_b = st.columns(2)
            
            # Tabela 1: Top Bilheterias
            with col_a:
                st.markdown("### 🏆 Top 20 Maiores Públicos")
                top_20 = df_filtered.sort_values('Publico', ascending=False).head(20)
                st.dataframe(
                    top_20[['Titulo', 'Ano_Exibicao', 'Publico', 'Renda']], 
                    hide_index=True,
                    use_container_width=True
                )
            
            # Tabela 2: Cauda Longa (Menores Bilheterias Válidas)
            with col_b:
                st.markdown("### 📉 Cauda Longa (Menores Bilheterias)")
                # Filtro de sanidade: Renda > 100 reais e Publico > 10 pessoas para evitar erros de leitura
                mask_sanity = (df_filtered['Renda'] > 100) & (df_filtered['Publico'] > 10)
                bottom_20 = df_filtered[mask_sanity].sort_values('Renda', ascending=True).head(20)
                st.dataframe(
                    bottom_20[['Titulo', 'Ano_Exibicao', 'Publico', 'Renda']], 
                    hide_index=True,
                    use_container_width=True
                )
            
            # Download
            csv = df_filtered.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Baixar Dataset Completo (Filtrado)",
                data=csv,
                file_name="dados_ancine_filtrados.csv",
                mime="text/csv"
            )

        with tab2:
            st.subheader("Evolução do Mercado")
            
            # Dados para gráficos (baseado no filtro anterior)
            df_year = df_filtered.groupby('Ano_Exibicao')[['Publico', 'Renda']].sum().reset_index()
            
            # Gráfico 1: Linha do Tempo
            fig_line = px.line(
                df_year, 
                x='Ano_Exibicao', 
                y='Publico', 
                title='Evolução do Público Total (Seleção Atual)',
                markers=True
            )
            st.plotly_chart(fig_line, use_container_width=True)
            
            # Gráfico 2: Scatter (Renda vs Público)
            fig_scatter = px.scatter(
                df_filtered, 
                x='Publico', 
                y='Renda', 
                hover_data=['Titulo'],
                title='Distribuição Renda vs. Público (Identificador de Outliers)',
                log_x=True, log_y=True # Escala logarítmica ajuda a ver a cauda longa
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        with tab3:
            st.subheader("Diagnóstico dos Dados Extraídos")
            st.metric("Total de Linhas Processadas", len(df_raw))
            st.metric("Total de Filmes Únicos", len(df_grouped))
            
            st.markdown("### Amostra dos Dados Brutos")
            st.dataframe(df_raw.head(10))
            
    else:
        st.warning("Nenhum dado válido encontrado. Verifique se o PDF é da 'Listagem de Filmes' da ANCINE.")

elif process_btn and not uploaded_files:
    st.warning("Por favor, faça upload de pelo menos um arquivo PDF.")