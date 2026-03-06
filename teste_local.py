import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import math
import datetime
import pytz
import time
import random

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="FOOBOT PRO", page_icon="⚽", layout="wide")

# # --- MOTOR DE IA (SINGLETON) ---
# --- CONFIGURAÇÃO DA IA (GEMINI 2.5) ---
@st.cache_resource
def configurar_ia():
    if "GEMINI_API_KEY" in st.secrets:
        try:
            chave = st.secrets["GEMINI_API_KEY"]
            genai.configure(api_key=chave, transport='rest')
            # Forçamos a 2.5 que é a que funcionou no seu PC
            return genai.GenerativeModel(model_name='gemini-2.5-flash')
        except Exception as e:
            st.error(f"Erro na configuração: {e}")
    return None

model = configurar_ia()

# --- FUNÇÃO DE ANÁLISE COM TRATAMENTO DE COTA ---
def gerar_analise_gemini(mandante, visitante, l_m, l_v, prob, cravada):
    if model is None: return "IA não configurada."
    
    prompt = f"Analise: {mandante} x {visitante}. Poisson: {cravada} ({prob:.1f}%). Dê um veredito curto."
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        # Se estourar a cota de 5 req/min do Gemini 2.5
        if "429" in str(e):
            return "⏳ Limite de velocidade atingido. Aguarde 30 segundos e tente novamente."
        return f"Erro na análise da IA: {e}"

# --- CONEXÃO COM GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

def validar_usuario(nome_digitado):
    try:
        df = conn.read(worksheet="Página1", ttl=0)
        user_row = df[df['nome'].str.lower() == nome_digitado.lower()]
        if not user_row.empty:
            creditos_atuais = user_row.iloc[0]['creditos']
            if creditos_atuais > 0:
                return True, int(creditos_atuais)
        return False, 0
    except:
        return False, 0

def descontar_credito(nome_digitado, saldo_atual):
    novo_saldo = saldo_atual - 1
    df_atualizado = conn.read(worksheet="Página1", ttl=0)
    df_atualizado.loc[df_atualizado['nome'].str.lower() == nome_digitado.lower(), 'creditos'] = novo_saldo
    conn.update(worksheet="Página1", data=df_atualizado)
    return novo_saldo

# --- INTERFACE DE ACESSO ---
st.sidebar.header("🔑 Acesso do Usuário")
nome_user = st.sidebar.text_input("Digite suas informações de login:")

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

# ==========================================
# 🛠️ MOCK DA API (AMBIENTE DE HOMOLOGAÇÃO)
# ==========================================
def fazer_requisicao(url, params=None):
    """Simula as respostas da API-Sports para testes."""
    time.sleep(0.3) 
    if params and "date" in params:
        return {
            "response": [
                {"fixture": {"id": 1001, "date": "2026-03-06T15:30:00+00:00", "status": {"short": "NS"}}, "league": {"name": "Bundesliga", "country": "Germany"}, "teams": {"home": {"id": 157, "name": "Bayern München"}, "away": {"id": 163, "name": "Borussia M'gladbach"}}},
                {"fixture": {"id": 1002, "date": "2026-03-08T16:00:00+00:00", "status": {"short": "NS"}}, "league": {"name": "Copa do Brasil", "country": "World"}, "teams": {"home": {"id": 120, "name": "Flamengo"}, "away": {"id": 121, "name": "Palmeiras"}}}
            ]
        }
    elif params and "last" in params:
        id_buscado = params["team"]
        return {"response": [{"teams": {"home": {"id": id_buscado}, "away": {"id": 999}}, "goals": {"home": random.randint(0,3), "away": random.randint(0,2)}} for _ in range(10)]}
    return {"response": []}

# --- FUNÇÃO DE IA ÚNICA E CORRIGIDA ---
def gerar_analise_gemini(mandante, visitante, l_m, l_v, prob, cravada):
    if model is None:
        return "IA não configurada corretamente."
    
    prompt = f"Analise o jogo {mandante} x {visitante}. Médias de gols: Mandante {l_m:.2f}, Visitante {l_v:.2f}. Placar provável: {cravada}. Confiança: {prob:.1f}%. Dê um veredito de aposta curto."
    
    try:
        # Usa o objeto model global que já foi validado
        response = model.generate_content(prompt)
        return response.text if response else "Sem resposta da IA"
    except Exception as e:
        return f"Erro na análise da IA: {e}"

# --- FUNÇÕES DE DADOS COM CACHE ---
@st.cache_data(ttl=3600)
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

@st.cache_data(ttl=3600)
def calcular_medias_ponderadas(id_time, local='home'):
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"team": id_time, "last": "10"} 
    response = fazer_requisicao(url, params) 
    jogos = response.get('response', [])
    if not jogos: return 1.35 
    gols_fator = [] 
    jogos_ordenados = list(reversed(jogos)) 
    for i, j in enumerate(jogos_ordenados):
        peso = 1 if i < 4 else (2 if i < 8 else 4)
        gols = j['goals']['home'] if j['teams']['home']['id'] == id_time else j['goals']['away']
        if (local == 'home' and j['teams']['home']['id'] == id_time) or (local == 'away' and j['teams']['away']['id'] == id_time):
            peso += 1
        if gols is not None:
            for _ in range(peso): gols_fator.append(gols)
    return pd.Series(gols_fator).mean() if gols_fator else 1.35

@st.cache_data(ttl=600)
def buscar_escalacoes(id_partida):
    return fazer_requisicao("url", params={"fixture": id_partida}).get('response', [])

def prob_poisson(media, gols):
    if media <= 0: media = 0.1
    return ((math.exp(-media) * (media ** gols)) / math.factorial(gols)) * 100

# --- INTERFACE PRINCIPAL ---
st.title("⚽ FOOBOT PRO AI - Homologação")

data_escolhida = st.date_input("Data dos jogos:", datetime.date.today())
df_jogos = buscar_jogos(data_escolhida.strftime('%Y-%m-%d'))

if not df_jogos.empty:
    def ligas_permitidas(row):
        if row['Pais'] == 'Brazil': return True
        if row['Pais'] == 'Germany' and row['Liga'] == 'Bundesliga': return True
        return True if row['Pais'] == 'World' and row['Liga'] == 'Copa do Brasil' else False
        
    df_jogos = df_jogos[df_jogos.apply(ligas_permitidas, axis=1)]

    if not df_jogos.empty:
        ligas_disponiveis = sorted(df_jogos['Liga'].unique().tolist())
        ligas_sel = st.multiselect("📍 Filtrar por Liga:", options=ligas_disponiveis)
        if ligas_sel: df_jogos = df_jogos[df_jogos['Liga'].isin(ligas_sel)]
        
        opcoes = df_jogos.apply(lambda x: f"[{x['Horario']}] {x['Mandante']} x {x['Visitante']} ({x['Liga']})", axis=1)
        if not opcoes.empty:
            jogo_sel = st.selectbox("Selecione a partida simulada:", opcoes.tolist())
            if st.button("🔮 Gerar Previsão com IA"):
                novo_saldo = descontar_credito(nome_user, saldo)
                st.session_state['mostrar_resultados'] = True
                st.sidebar.warning(f"Crédito utilizado! Saldo: {novo_saldo}")
                st.rerun()

            if st.session_state.get('mostrar_resultados', False):
                with st.spinner('O Modelo Matemático e a IA estão analisando os dados...'):
                    idx = opcoes.tolist().index(jogo_sel)
                    j_d = df_jogos.iloc[idx]
                    l_m = calcular_medias_ponderadas(j_d['ID_Mandante'], 'home')
                    l_v = calcular_medias_ponderadas(j_d['ID_Visitante'], 'away')
                    
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
                    placar_cravada = df_res.iloc[0]['Placar']
                    
                    st.success(f"🎯 **CRAVADA RECOMENDADA:** {placar_cravada} ({df_res.iloc[0]['Prob']:.2f}%)")

                    st.markdown("---")
                    st.markdown("### 🤖 Veredito da Inteligência Artificial (Gemini)")
                    with st.spinner("Gemini escrevendo análise..."):
                        analise_texto = gerar_analise_gemini(j_d['Mandante'], j_d['Visitante'], l_m, l_v, prob_tendencia, placar_cravada)
                        st.info(analise_texto)

                    st.markdown("---")
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
                        st.dataframe(df_t[['Placar', 'Probabilidade (%)']], hide_index=True, use_container_width=True)