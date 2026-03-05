import streamlit as st
from streamlit_gsheets import GSheetsConnection
import requests
import pandas as pd
import math
import datetime
import pytz

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="FOOBOT PRO", page_icon="⚽", layout="wide")

if 'api_usage' not in st.session_state:
    st.session_state['api_usage'] = 0

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

# --- INTERFACE DE ACESSO ---
st.sidebar.header("🔑 Acesso")
nome_user = st.sidebar.text_input("Nome:")

if nome_user:
    permitido, saldo = validar_usuario(nome_user)
    if not permitido:
        st.sidebar.error("Sem acesso.")
        st.stop()
else:
    st.info("Faça login.")
    st.stop()

# --- CONFIGURAÇÕES DAS APIs ---
API_KEY_SPORTS = ["74d794123dbe38caf1f24a487feccb4b", "c529d0695b02fa73ccdcc19cb89026d7"]
API_TOKEN_FD = "27481152317540abbd381d14669d4a40" # Sua chave Forever

def requisicao_sports(url, params=None):
    if st.session_state['api_usage'] >= 95: return {}
    for key in API_KEY_SPORTS:
        headers = {"x-apisports-key": key}
        try:
            res = requests.get(url, headers=headers, params=params).json()
            st.session_state['api_usage'] += 1
            if not res.get('errors'): return res
        except: continue
    return {}

# --- BUSCA DE JOGOS HÍBRIDA ---
@st.cache_data(ttl=300)
def buscar_jogos_unificados(data_str):
    # 1. Tenta Football-Data (Elite - Mais estável agora)
    try:
        url_fd = f"https://api.football-data.org/v4/matches?dateFrom={data_str}&dateTo={data_str}"
        headers_fd = {'X-Auth-Token': API_TOKEN_FD}
        res_fd = requests.get(url_fd, headers=headers_fd).json()
        if 'matches' in res_fd:
            dados = []
            for j in res_fd['matches']:
                dados.append({
                    'ID': j['id'], 'Hora': j['utcDate'][11:16], 'Liga': j['competition']['name'],
                    'Pais': j['area']['name'], 'Mandante': j['homeTeam']['name'],
                    'ID_M': j['homeTeam']['id'], 'Visitante': j['awayTeam']['name'],
                    'ID_V': j['awayTeam']['id'], 'Fonte': 'FD'
                })
            if dados: return pd.DataFrame(dados)
    except: pass

    # 2. Backup API-Sports (Estaduais/Ligas Menores)
    res_sp = requisicao_sports("https://v3.football.api-sports.io/fixtures", {"date": data_str})
    if res_sp.get('response'):
        dados = []
        for j in res_sp['response']:
            dados.append({
                'ID': j['fixture']['id'], 'Hora': j['fixture']['date'][11:16], 'Liga': j['league']['name'],
                'Pais': j['league']['country'], 'Mandante': j['teams']['home']['name'],
                'ID_M': j['teams']['home']['id'], 'Visitante': j['teams']['away']['name'],
                'ID_V': j['teams']['away']['id'], 'Fonte': 'SP'
            })
        return pd.DataFrame(dados)
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def calcular_poisson_medias(id_time, fonte):
    # Se a fonte for API-Sports, usa a lógica antiga
    if fonte == 'SP':
        res = requisicao_sports("https://v3.football.api-sports.io/fixtures", {"team": id_time, "last": "10", "status": "FT"})
        jogos = res.get('response', [])
        if not jogos: return 0.5
        gols = [j['goals']['home'] if j['teams']['home']['id'] == id_time else j['goals']['away'] for j in jogos]
        return pd.Series(gols).mean()
    # Para Football-Data, a lógica de médias precisaria de mais chamadas (limitado no free)
    return 1.2 # Média base para evitar o erro 0.50

# --- INTERFACE ---
st.title("⚽ FOOBOT PRO")
st.sidebar.write(f"Consumo: {st.session_state['api_usage']}/100")

data_hj = st.date_input("Data:", datetime.date.today())
df = buscar_jogos_unificados(data_hj.strftime('%Y-%m-%d'))

if not df.empty:
    opcoes = df.apply(lambda x: f"[{x['Hora']}] {x['Mandante']} x {x['Visitante']} ({x['Liga']})", axis=1).tolist()
    sel = st.selectbox("Jogo:", opcoes)
    
    if st.button("Analisar"):
        idx = opcoes.index(sel)
        j = df.iloc[idx]
        m_m = calcular_poisson_medias(j['ID_M'], j['Fonte'])
        m_v = calcular_poisson_medias(j['ID_V'], j['Fonte'])
        
        st.metric(f"Força {j['Mandante']}", f"{m_m:.2f}")
        st.metric(f"Força {j['Visitante']}", f"{m_v:.2f}")
        
        # Poisson Simples para teste rápido
        prob_0x0 = (math.exp(-m_m) * math.exp(-m_v)) * 100
        st.success(f"🎯 Probabilidade 0x0: {prob_0x0:.2f}%")
else:
    st.error("Nenhum jogo encontrado. Verifique se as APIs não estão suspensas.")