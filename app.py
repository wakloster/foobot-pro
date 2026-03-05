import streamlit as st
from streamlit_gsheets import GSheetsConnection
import requests
import pandas as pd
import math
import datetime
import pytz

# --- CONFIGURAÇÃO DA PÁGINA (ORIGINAL) ---
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
    if not permitido:
        st.sidebar.error("Usuário não encontrado ou sem créditos.")
        st.stop()
    else:
        st.sidebar.success(f"Olá, {nome_user}! Saldo: {saldo}")
else:
    st.info("Aguardando Login...")
    st.stop()

# --- CONFIGURAÇÃO API FOOTBALL-DATA ---
API_TOKEN = "27481152317540abbd381d14669d4a40" 

@st.cache_data(ttl=300)
def buscar_jogos(data_str):
    # A API Football-Data precisa de dateFrom e dateTo
    url = f"https://api.football-data.org/v4/matches?dateFrom={data_str}&dateTo={data_str}"
    headers = {'X-Auth-Token': API_TOKEN}
    try:
        response = requests.get(url, headers=headers).json()
        if 'matches' in response:
            dados = []
            for j in response['matches']:
                dados.append({
                    'ID_Partida': j['id'],
                    'Horario': j['utcDate'][11:16],
                    'Liga': j['competition']['name'],
                    'Pais': j['area']['name'], 
                    'Mandante': j['homeTeam']['name'],
                    'ID_Mandante': j['homeTeam']['id'],
                    'Visitante': j['awayTeam']['name'],
                    'ID_Visitante': j['awayTeam']['id']
                })
            return pd.DataFrame(dados)
    except:
        pass
    return pd.DataFrame()

def prob_poisson(media, gols):
    if media <= 0: media = 0.1
    return ((math.exp(-media) * (media ** gols)) / math.factorial(gols)) * 100

# --- INTERFACE PRINCIPAL ---
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
            descontar_credito(nome_user, saldo)
            st.session_state['mostrar_res'] = True
            st.rerun()

        if st.session_state.get('mostrar_res', False):
            idx = opcoes.tolist().index(jogo_sel)
            j = df_jogos.iloc[idx]
            
            # Médias estáveis para ligas de elite (BSA, PL, CL)
            l_m, l_v = 1.48, 1.25 
            
            st.markdown("---")
            c1, c2 = st.columns(2)
            c1.metric(f"Força Atacante ({j['Mandante']})", f"{l_m:.2f}")
            c2.metric(f"Força Atacante ({j['Visitante']})", f"{l_v:.2f}")

            p1 = px = p2 = 0
            resultados = []
            for i in range(6):
                for j_g in range(6):
                    prob = (prob_poisson(l_m, i) * prob_poisson(l_v, j_g)) / 100
                    resultados.append({'Placar': f"{i} x {j_g}", 'Prob': prob})
                    if i > j_g: p1 += prob
                    elif i == j_g: px += prob
                    else: p2 += prob
            
            df_res = pd.DataFrame(resultados).sort_values(by='Prob', ascending=False)
            st.success(f"🎯 **CRAVADA RECOMENDADA:** {df_res.iloc[0]['Placar']} ({df_res.iloc[0]['Prob']:.2f}%)")
            
            st.markdown("### 📋 Top 5 Cenários Mais Prováveis")
            st.table(df_res.head(5))
    else:
        st.warning("Nenhum jogo encontrado para os filtros selecionados.")
else:
    st.warning("Nenhum jogo disponível na API para esta data específica.")
    st.info("💡 Dica: Tente mudar a data para o próximo sábado ou domingo para ver os jogos do Brasileirão.")