import streamlit as st
from streamlit_gsheets import GSheetsConnection
import requests
import pandas as pd
import math
import datetime
import pytz

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="FOOBOT PRO", page_icon="⚽", layout="wide")

# Inicializa contador de uso para evitar banimento (Limite 100/dia)
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

# --- INTERFACE DE ACESSO (SIDEBAR) ---
st.sidebar.header("🔑 Acesso do Usuário")
nome_user = st.sidebar.text_input("Digite seu primeiro nome:")

if nome_user:
    permitido, saldo = validar_usuario(nome_user)
    if não permitido:
        st.sidebar.error("Usuário não encontrado ou sem créditos.")
        st.stop()
    else:
        st.sidebar.success(f"Olá, {nome_user}! Você tem {saldo} créditos.")
else:
    st.info("Digite suas informações de login para liberar acesso.")
    st.stop()

# --- CONFIGURAÇÕES DAS APIs ---
API_KEY_SPORTS = [
    "74d794123dbe38caf1f24a487feccb4b", # Chave do Eliabe
    "c529d0695b02fa73ccdcc19cb89026d7"  # Sua principal (Reset às 21h)
]
API_TOKEN_FD = "27481152317540abbd381d14669d4a40" # Sua chave Forever do print

# --- BLOCO DE DIAGNÓSTICO (O BOTÃO DE TESTE) ---
st.title("⚽ FOOBOT PRO - Analista de Elite")

if st.button("🔌 Testar Conexão Direta (Brasileirão)"):
    url_teste = "https://api.football-data.org/v4/competitions/BSA/matches?status=SCHEDULED"
    headers_fd = {'X-Auth-Token': API_TOKEN_FD}
    try:
        res = requests.get(url_teste, headers=headers_fd).json()
        if 'matches' in res:
            st.success(f"✅ Conexão OK! Encontrados {len(res['matches'])} jogos agendados.")
            if res['matches']:
                st.write("Exemplo de jogo encontrado:", res['matches'][0]['homeTeam']['name'], "x", res['matches'][0]['awayTeam']['name'])
        else:
            st.error(f"❌ Erro na API: {res}")
    except Exception as e:
        st.error(f"❌ Falha de Conexão: {e}")

# --- FUNÇÕES DE DADOS ---
def fazer_requisicao_sports(url, params=None):
    if st.session_state['api_usage'] >= 95:
        st.error("⚠️ Limite de segurança (95/100) atingido.")
        return {}
    for key in API_KEY_SPORTS:
        headers = {"x-apisports-key": key}
        try:
            response = requests.get(url, headers=headers, params=params).json()
            st.session_state['api_usage'] += 1
            if not response.get('errors'): return response
        except: continue
    return {}

@st.cache_data(ttl=300)
def buscar_jogos_unificados(data_str):
    # Tenta Football-Data primeiro (Ligas Elite)
    try:
        url_fd = f"https://api.football-data.org/v4/matches?dateFrom={data_str}&dateTo={data_str}"
        headers_fd = {'X-Auth-Token': API_TOKEN_FD}
        res_fd = requests.get(url_fd, headers=headers_fd).json()
        if 'matches' in res_fd and res_fd['matches']:
            dados = []
            for j in res_fd['matches']:
                dados.append({
                    'ID': j['id'], 'Hora': j['utcDate'][11:16], 'Liga': j['competition']['name'],
                    'Pais': j['area']['name'], 'Mandante': j['homeTeam']['name'],
                    'ID_M': j['homeTeam']['id'], 'Visitante': j['awayTeam']['name'],
                    'ID_V': j['awayTeam']['id'], 'Fonte': 'Football-Data'
                })
            return pd.DataFrame(dados)
    except: pass

    # Backup API-Sports (Estaduais)
    res_sp = fazer_requisicao_sports("https://v3.football.api-sports.io/fixtures", {"date": data_str})
    if res_sp.get('response'):
        dados = []
        for j in res_sp['response']:
            dados.append({
                'ID': j['fixture']['id'], 'Hora': j['fixture']['date'][11:16], 'Liga': j['league']['name'],
                'Pais': j['league']['country'], 'Mandante': j['teams']['home']['name'],
                'ID_M': j['teams']['home']['id'], 'Visitante': j['teams']['away']['name'],
                'ID_V': j['teams']['away']['id'], 'Fonte': 'API-Sports'
            })
        return pd.DataFrame(dados)
    return pd.DataFrame()

@st.cache_data(ttl=86400) # Cache de 24h para médias de gols
def calcular_medias(id_time, fonte):
    if fonte == 'API-Sports':
        res = fazer_requisicao_sports("https://v3.football.api-sports.io/fixtures", {"team": id_time, "last": "10", "status": "FT"})
        jogos = res.get('response', [])
        if not jogos: return 1.2
        gols = [j['goals']['home'] if j['teams']['home']['id'] == id_time else j['goals']['away'] for j in jogos]
        return pd.Series(gols).mean()
    return 1.4 # Média base para a nova API enquanto não integramos o histórico dela

def prob_poisson(media, gols):
    if media <= 0: media = 0.1
    return ((math.exp(-media) * (media ** gols)) / math.factorial(gols)) * 100

# --- LÓGICA PRINCIPAL ---
st.sidebar.write(f"📊 Uso API: {st.session_state['api_usage']}/100")
data_escolhida = st.date_input("Data dos jogos:", datetime.date.today())
df_jogos = buscar_jogos_unificados(data_escolhida.strftime('%Y-%m-%d'))

if not df_jogos.empty:
    opcoes = df_jogos.apply(lambda x: f"[{x['Hora']}] {x['Mandante']} x {x['Visitante']} ({x['Liga']})", axis=1).tolist()
    jogo_sel = st.selectbox("Selecione a partida:", opcoes)
    
    if st.button("🔮 Gerar Previsão"):
        saldo = descontar_credito(nome_user, saldo)
        st.session_state['ver_res'] = True
        st.rerun()

    if st.session_state.get('ver_res', False):
        idx = opcoes.index(jogo_sel)
        j = df_jogos.iloc[idx]
        m_m = calcular_medias(j['ID_M'], j['Fonte'])
        m_v = calcular_medias(j['ID_V'], j['Fonte'])
        
        c1, c2 = st.columns(2)
        c1.metric(f"Força {j['Mandante']}", f"{m_m:.2f}")
        c2.metric(f"Força {j['Visitante']}", f"{m_v:.2f}")
        
        prob_0x0 = (prob_poisson(m_m, 0) * prob_poisson(m_v, 0)) / 100
        st.success(f"🎯 Probabilidade 0x0: {prob_0x0:.2f}% (Fonte: {j['Fonte']})")
else:
    st.warning("Nenhum jogo encontrado para esta data nas APIs ativas.")