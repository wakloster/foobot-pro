import streamlit as st
from streamlit_gsheets import GSheetsConnection
import requests
import pandas as pd
import math
import datetime
import pytz
import time  # <--- IMPORTADO AQUI

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

# --- CONFIGURAÇÕES DA API ---
API_KEYS = ["b6fad616c22249eb28bba395de1b20fc"] 

def fazer_requisicao(url, params=None):
    if st.session_state['api_usage'] >= 95:
        st.error("⚠️ Limite de segurança atingido (95/100).")
        return {}
    for key in API_KEYS:
        headers = {"x-apisports-key": key}
        try:
            # O PULO DO GATO: Pausa para a API não dar block de Rate Limit
            time.sleep(1.2) 
            response = requests.get(url, headers=headers, params=params).json()
            st.session_state['api_usage'] += 1
            if not response.get('errors'):
                return response
        except:
            continue
    return {}

@st.cache_data(ttl=60)
def buscar_jogos(data_str):
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"date": data_str}
    response = fazer_requisicao(url, params)
    
    if not response or 'response' not in response or not response['response']:
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
    
    if not jogos: 
        return None 
    
    gols_fator = [] 
    jogos_ordenados = list(reversed(jogos)) 
    for i, j in enumerate(jogos_ordenados):
        peso = 1 if i < 4 else (2 if i < 8 else 4)
        gols = j['goals']['home'] if j['teams']['home']['id'] == id_time else j['goals']['away']
        if (local == 'home' and j['teams']['home']['id'] == id_time) or (local == 'away' and j['teams']['away']['id'] == id_time):
            peso += 1
        if gols is not None:
            for _ in range(peso): gols_fator.append(gols)
            
    return pd.Series(gols_fator).mean() if gols_fator else None

@st.cache_data(ttl=60)
def buscar_escalacoes(id_partida):
    url = "https://v3.football.api-sports.io/fixtures/lineups"
    params = {"fixture": id_partida}
    response = fazer_requisicao(url, params)
    return response.get('response', [])

def prob_poisson(media, gols):
    if media <= 0: media = 0.1
    return ((math.exp(-media) * (media ** gols)) / math.factorial(gols)) * 100

# --- INTERFACE PRINCIPAL ---
st.title("⚽ FOOBOT PRO - Analista de Elite")
st.sidebar.write(f"📊 Uso da API: {st.session_state['api_usage']}/100")

data_escolhida = st.date_input("Escolha a data:", datetime.date.today(), format="DD/MM/YYYY")
df_jogos = buscar_jogos(data_escolhida.strftime('%Y-%m-%d'))

if df_jogos.empty:
    st.warning("⚠️ Nenhum jogo encontrado para esta data na API.")
else:
    def ligas_vip(row):
        paises_vip = ['Brazil', 'England', 'Spain', 'Germany', 'Italy', 'France']
        ligas_world = ['UEFA Champions League', 'UEFA Europa League', 'Copa Libertadores', 'Copa Sudamericana']
        return row['Pais'] in paises_vip or (row['Pais'] == 'World' and row['Liga'] in ligas_world)

    df_vip = df_jogos[df_jogos.apply(ligas_vip, axis=1)]
    
    if df_vip.empty:
        st.info("📅 Sem jogos de elite hoje. Tente mudar a data para o final de semana.")
    else:
        opcoes = df_vip.apply(lambda x: f"[{x['Horario']}] {x['Mandante']} x {x['Visitante']} ({x['Liga']})", axis=1)
        jogo_sel = st.selectbox("Selecione a partida:", opcoes.tolist())
        
        if st.button("🔮 Gerar Previsão de Elite"):
            st.session_state['mostrar_resultados'] = True
            st.rerun()

        if st.session_state.get('mostrar_resultados', False):
            with st.spinner('Analisando dados (evitando bloqueios da API)...'):
                idx = opcoes.tolist().index(jogo_sel)
                j_d = df_vip.iloc[idx]
                
                # As chamadas agora têm 1.2s de intervalo natural graças ao time.sleep
                l_m = calcular_medias_ponderadas(j_d['ID_Mandante'], 'home')
                l_v = calcular_medias_ponderadas(j_d['ID_Visitante'], 'away')
                
                if l_m is None or l_v is None:
                    st.error("❌ Não foi possível calcular a predição: Histórico de jogos insuficiente na API.")
                else:
                    descontar_credito(nome_user, saldo)
                    st.markdown("---")
                    st.markdown("### 📋 Escalações Oficiais")
                    lineups = buscar_escalacoes(j_d['ID_Partida'])
                    if lineups:
                        c_esc1, c_esc2 = st.columns(2)
                        for i, t in enumerate(lineups):
                            col = c_esc1 if i == 0 else c_esc2
                            with col:
                                st.subheader(f"{t['team']['name']} ({t['formation']})")
                                st.caption(f"**Titulares:** {', '.join([p['player']['name'] for p in t['startXI']])}")
                    else: 
                        st.info("🕒 Escalações oficiais disponíveis 40 min antes.")
                        
                    st.markdown("---")
                    c1, c2 = st.columns(2)
                    c1.metric(f"Força Atacante ({j_d['Mandante']})", f"{l_m:.2f}")
                    c2.metric(f"Fragilidade Defensiva ({j_d['Visitante']})", f"{l_v:.2f}")

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
                    prob_tendencia = max(p1, px, p2)
                    
                    st.write("### 🌡️ Nível de Confiança do Modelo")
                    st.progress(min(prob_tendencia * 2 / 100, 1.0))
                    st.write(f"Confiança: **{prob_tendencia:.1f}%**")
                    st.success(f"🎯 **CRAVADA RECOMENDADA:** {df_res.iloc[0]['Placar']} ({df_res.iloc[0]['Prob']:.2f}%)")
                    
                    col_g, col_t = st.columns([1.2, 1])
                    with col_g:
                        st.markdown("### 📊 Top 5 Placares")
                        df_g = df_res.head(5).copy()
                        df_g['Probabilidade (%)'] = df_g['Prob'].round(2)
                        st.bar_chart(data=df_g, x='Placar', y='Probabilidade (%)')
                    with col_t:
                        st.markdown("### 📋 Top 10 Cenários")
                        df_t = df_res.head(10).copy()
                        df_t['Probabilidade (%)'] = df_t['Prob'].apply(lambda x: f"{x:.2f}%")
                        st.dataframe(df_t[['Placar', 'Probabilidade (%)']], hide_index=True)