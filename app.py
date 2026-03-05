import streamlit as st
from streamlit_gsheets import GSheetsConnection
import requests
import pandas as pd
import math
import datetime
import pytz

# --- CONFIGURAÇÃO DA PÁGINA ---
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

# --- INTERFACE DE ACESSO ---
st.sidebar.header("🔑 Acesso do Usuário")
nome_user = st.sidebar.text_input("Digite seu primeiro nome:")

if nome_user:
    permitido, saldo = validar_usuario(nome_user)
    if permitido:
        st.sidebar.success(f"Olá, {nome_user}! Você tem {saldo} créditos.")
    else:
        st.sidebar.error("Usuário não encontrado.")
        st.stop()
else:
    st.info("Digite suas informações de login.")
    st.stop()

# --- CONFIGURAÇÕES DA API ---
API_KEYS = ["74d794123dbe38caf1f24a487feccb4b", "c529d0695b02fa73ccdcc19cb89026d7"]

def fazer_requisicao(url, params=None):
    for key in API_KEYS:
        headers = {"x-apisports-key": key}
        response = requests.get(url, headers=headers, params=params).json()
        if not response.get('errors'):
            return response
    return {}

# --- FUNÇÕES DE DADOS ---
@st.cache_data(ttl=300)
def buscar_jogos(data_str):
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"date": data_str}
    response = fazer_requisicao(url, params)
    
    if not response or 'response' not in response:
        return pd.DataFrame()

    dados = []
    fuso_br = pytz.timezone('America/Sao_Paulo')
    for jogo in response['response']:
        status = jogo['fixture']['status']['short']
        if status in ['NS', '1H', 'HT', '2H', 'LIVE']:
            data_utc = datetime.datetime.fromisoformat(jogo['fixture']['date'].replace('Z', '+00:00'))
            data_br = data_utc.astimezone(fuso_br)
            dados.append({
                'ID_Partida': jogo['fixture']['id'],
                'Horario': data_br.strftime('%H:%M'),
                'Liga': jogo['league']['name'],
                'Pais': jogo['league']['country'], 
                'Mandante': jogo['teams']['home']['name'],
                'ID_Mandante': jogo['teams']['home']['id'],
                'Visitante': jogo['teams']['away']['name'],
                'ID_Visitante': jogo['teams']['away']['id']
            })
    return pd.DataFrame(dados)

@st.cache_data(ttl=86400)
def calcular_medias_ponderadas(id_time, local='home'):
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"team": id_time, "last": "10", "status": "FT"} 
    response = fazer_requisicao(url, params)
    jogos = response.get('response', [])
    if not jogos: return 0.5 
    gols_fator = [j['goals']['home'] if j['teams']['home']['id'] == id_time else j['goals']['away'] for j in jogos]
    return pd.Series(gols_fator).mean()

def prob_poisson(media, gols):
    if media <= 0: media = 0.1
    return ((math.exp(-media) * (media ** gols)) / math.factorial(gols)) * 100

# --- INTERFACE PRINCIPAL ---
st.title("⚽ FOOBOT PRO - Analista de Elite")

data_escolhida = st.date_input("Data dos jogos:", datetime.date.today(), format="DD/MM/YYYY")
df_jogos = buscar_jogos(data_escolhida.strftime('%Y-%m-%d'))

if not df_jogos.empty:
    # --- FILTRO DAS LIGAS DE ELITE (RESTAURADO) ---
    def ligas_permitidas(row):
        # Tudo do Brasil
        if row['Pais'] == 'Brazil': return True
        # Elite Europa
        if row['Pais'] == 'England' and row['Liga'] == 'Premier League': return True
        if row['Pais'] == 'Spain' and row['Liga'] == 'La Liga': return True
        if row['Pais'] == 'Germany' and row['Liga'] == 'Bundesliga': return True
        if row['Pais'] == 'Italy' and row['Liga'] == 'Serie A': return True
        # Torneios Continentais
        ligas_mundiais = ['UEFA Champions League', 'Copa Libertadores', 'Copa Sudamericana']
        return True if row['Pais'] == 'World' and row['Liga'] in ligas_mundiais else False

    df_jogos = df_jogos[df_jogos.apply(ligas_permitidas, axis=1)]

    if not df_jogos.empty:
        ligas_disponiveis = sorted(df_jogos['Liga'].unique().tolist())
        ligas_sel = st.multiselect("📍 Filtrar por Liga (Lista VIP):", options=ligas_disponiveis)
        if ligas_sel: df_jogos = df_jogos[df_jogos['Liga'].isin(ligas_sel)]
        
        opcoes = df_jogos.apply(lambda x: f"[{x['Horario']}] {x['Mandante']} x {x['Visitante']} ({x['Liga']})", axis=1)
        if not opcoes.empty:
            jogo_sel = st.selectbox("Selecione a partida:", opcoes.tolist())
            if st.button("🔮 Gerar Previsão de Elite"):
                saldo = descontar_credito(nome_user, saldo)
                st.session_state['ver_res'] = True
                st.rerun()

            if st.session_state.get('ver_res', False):
                idx = opcoes.tolist().index(jogo_sel)
                j = df_jogos.iloc[idx]
                m_m = calcular_medias_ponderadas(j['ID_Mandante'], 'home')
                m_v = calcular_medias_ponderadas(j['ID_Visitante'], 'away')
                
                st.markdown("---")
                c1, c2 = st.columns(2)
                c1.metric(f"Força {j['Mandante']}", f"{m_m:.2f}")
                c2.metric(f"Força {j['Visitante']}", f"{m_v:.2f}")
                
                prob_0x0 = (prob_poisson(m_m, 0) * prob_poisson(m_v, 0)) / 100
                st.success(f"🎯 **CRAVADA:** 0x0 ({prob_0x0:.2f}%)")
    else:
        st.warning("Nenhum jogo das Ligas VIP encontrado para hoje.")
else:
    st.info("Aguardando reset da API às 21h...")