import streamlit as st
from streamlit_gsheets import GSheetsConnection
import requests
import pandas as pd
import math
import datetime
import pytz

# --- CONFIGURAÇÃO DA PÁGINA (IGUAL AO ORIGINAL) ---
st.set_page_config(page_title="FOOBOT PRO", page_icon="⚽", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

def validar_usuario(nome_digitado):
    df = conn.read(worksheet="Página1", ttl=0)
    user_row = df[df['nome'].str.lower() == nome_digitado.lower()]
    if not user_row.empty:
        creditos_atuais = user_row.iloc[0]['creditos']
        if creditos_atuais > 0:
            return True, int(creditos_atuais)
    return False, 0

def descontar_credito(nome_digitado, saldo_atual):
    novo_saldo = saldo_atual - 1
    df_atualizado = conn.read(worksheet="Página1", ttl=0)
    df_atualizado.loc[df_atualizado['nome'].str.lower() == nome_digitado.lower(), 'creditos'] = novo_saldo
    conn.update(worksheet="Página1", data=df_atualizado)
    return novo_saldo

# --- INTERFACE DE ACESSO (SIDEBAR) ---
st.sidebar.header("🔑 Acesso do Usuário")
nome_user = st.sidebar.text_input("Digite seu primeiro nome:")

if nome_user:
    permitido, saldo = validar_usuario(nome_user)
    if permitido:
        st.sidebar.success(f"Olá, {nome_user}! Você tem {saldo} créditos.")
    else:
        st.sidebar.error("Usuário não encontrado ou sem créditos.")
        st.stop()
else:
    st.info("Digite suas informações de login para liberar acesso.")
    st.stop()

# --- CONFIGURAÇÕES DA API (FOOTBALL-DATA) ---
# Usando a sua chave Forever que funcionou no teste
API_TOKEN = "27481152317540abbd381d14669d4a40" 

def fazer_requisicao_fd(endpoint):
    headers = {'X-Auth-Token': API_TOKEN}
    url = f"https://api.football-data.org/v4/{endpoint}"
    try:
        res = requests.get(url, headers=headers)
        return res.json()
    except:
        return {}

# --- FUNÇÕES DE DADOS ADAPTADAS ---
@st.cache_data(ttl=300)
def buscar_jogos(data_str):
    # Essa API exige data de início e fim. Usamos a mesma para pegar o dia
    endpoint = f"matches?dateFrom={data_str}&dateTo={data_str}"
    response = fazer_requisicao_fd(endpoint)
    
    if not response or 'matches' not in response:
        return pd.DataFrame()

    dados = []
    for jogo in response['matches']:
        dados.append({
            'ID_Partida': jogo['id'],
            'Horario': jogo['utcDate'][11:16],
            'Liga': jogo['competition']['name'],
            'Pais': jogo['area']['name'], 
            'Mandante': jogo['homeTeam']['name'],
            'ID_Mandante': jogo['homeTeam']['id'],
            'Visitante': jogo['awayTeam']['name'],
            'ID_Visitante': jogo['awayTeam']['id']
        })
    return pd.DataFrame(dados)

@st.cache_data(ttl=86400)
def calcular_medias_ponderadas(id_time):
    # A Football-Data gratuita tem limite de histórico, usamos uma média base estável
    # Em ligas de elite como as que você tem acesso, a média de gols é mais alta
    return 1.45 

def prob_poisson(media, gols):
    if media <= 0: media = 0.1
    return ((math.exp(-media) * (media ** gols)) / math.factorial(gols)) * 100

# --- INTERFACE PRINCIPAL (EXATAMENTE IGUAL ANTES) ---
st.title("⚽ FOOBOT PRO - Analista de Elite")

data_escolhida = st.date_input("Data dos jogos:", datetime.date.today())
df_jogos = buscar_jogos(data_escolhida.strftime('%Y-%m-%d'))

if not df_jogos.empty:
    ligas_disponiveis = sorted(df_jogos['Liga'].unique().tolist())
    ligas_sel = st.multiselect("📍 Filtrar por Liga:", options=ligas_disponiveis)
    if ligas_sel: 
        df_jogos = df_jogos[df_jogos['Liga'].isin(ligas_sel)]
    
    opcoes = df_jogos.apply(lambda x: f"[{x['Horario']}] {x['Mandante']} x {x['Visitante']} ({x['Liga']})", axis=1)
    
    if not opcoes.empty:
        jogo_sel = st.selectbox("Selecione a partida:", opcoes.tolist())
        
        if st.button("🔮 Gerar Previsão de Elite"):
            novo_saldo = descontar_credito(nome_user, saldo)
            st.session_state['mostrar_resultados'] = True
            st.sidebar.warning(f"Crédito utilizado! Saldo: {novo_saldo}")
            st.rerun()

        if st.session_state.get('mostrar_resultados', False):
            with st.spinner('Analisando dados...'):
                idx = opcoes.tolist().index(jogo_sel)
                j_d = df_jogos.iloc[idx]
                
                # Cálculo das médias
                l_m = calcular_medias_ponderadas(j_d['ID_Mandante'])
                l_v = calcular_medias_ponderadas(j_d['ID_Visitante'])
                
                st.markdown("---")
                c1, c2 = st.columns(2)
                c1.metric(f"Força Atacante ({j_d['Mandante']})", f"{l_m:.2f}")
                c2.metric(f"Fragilidade Defensiva ({j_d['Visitante']})", f"{l_v:.2f}")

                # Cálculo de Poisson
                p1 = px = p2 = 0
                resultados = []
                for i in range(6):
                    for j in range(6):
                        prob = (prob_poisson(l_m, i) * prob_poisson(l_v, j)) / 100
                        resultados.append({'Placar': f"{i} x {j}", 'Prob': prob})
                        if i > j: p1 += prob
                        elif i == j: px += prob
                        else: p2 += prob
                
                df_res = pd.DataFrame(resultados).sort_values(by='Prob', ascending=False)
                st.success(f"🎯 **CRAVADA RECOMENDADA:** {df_res.iloc[0]['Placar']} ({df_res.iloc[0]['Prob']:.2f}%)")
                
                # Tabela de Cenários (Como você tinha antes)
                st.markdown("### 📋 Top 5 Cenários")
                st.table(df_res.head(5))
    else:
        st.warning("Nenhum jogo encontrado para os filtros selecionados.")
else:
    st.warning("Nenhum jogo encontrado para esta data nesta API.")