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
    df = conn.read(worksheet="Página1", ttl=0) # ttl=0 para ler dados frescos
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

# --- CONFIGURAÇÕES DA API (SISTEMA DE FAILOVER) ---
API_KEYS = [
    "7ae631412b052dece78c1876932d3c92", # CHAVE NOVA (Primária)
    "c529d0695b02fa73ccdcc19cb89026d7"  # CHAVE ANTIGA (Backup)
]

def fazer_requisicao(url, params=None):
    """Tenta fazer a requisição iterando pelas chaves da API até conseguir sucesso."""
    for key in API_KEYS:
        headers = {"x-apisports-key": key}
        response = requests.get(url, headers=headers, params=params).json()
        
        # A API-Sports retorna o campo 'errors' (como dicionário ou lista) quando há falha de token/limite
        erros = response.get('errors', [])
        if not erros:
            return response # Sucesso! Retorna os dados.
            
        # Se chegou aqui, a chave atual falhou (passou do limite). Tenta a próxima do loop.
        
    # Se esgotar TODAS as chaves, retorna um dicionário vazio
    return {}

# --- FUNÇÕES DE DADOS COM CACHE ---
@st.cache_data(ttl=3600)
def buscar_jogos(data_str):
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"date": data_str}
    response = requests.get(url, headers=HEADERS, params=params).json()
    
    if 'response' not in response or not response['response']:
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
    params = {"team": id_time, "last": "10", "status": "FT"} 
    response = requests.get(url, headers=HEADERS, params=params).json()
    jogos = response.get('response', [])
    if not jogos: return 0.5 
    
    gols_fator = [] 
    jogos.reverse() 
    for i, j in enumerate(jogos):
        if i < 4: peso = 1
        elif i < 8: peso = 2
        else: peso = 4
        
        gols = j['goals']['home'] if j['teams']['home']['id'] == id_time else j['goals']['away']
        if (local == 'home' and j['teams']['home']['id'] == id_time) or \
           (local == 'away' and j['teams']['away']['id'] == id_time):
            peso += 1
            
        for _ in range(peso):
            gols_fator.append(gols)
    return pd.Series(gols_fator).mean()

@st.cache_data(ttl=600)
def buscar_escalacoes(id_partida):
    url = "https://v3.football.api-sports.io/fixtures/lineups"
    params = {"fixture": id_partida}
    response = requests.get(url, headers=HEADERS, params=params).json()
    return response.get('response', [])

def prob_poisson(media, gols):
    if media <= 0: media = 0.1
    return ((math.exp(-media) * (media ** gols)) / math.factorial(gols)) * 100

# --- INTERFACE PRINCIPAL ---
st.title("⚽ FOOBOT PRO - Analista de Elite")

data_escolhida = st.date_input("Data dos jogos:", datetime.date.today(), format="DD/MM/YYYY")
df_jogos = buscar_jogos(data_escolhida.strftime('%Y-%m-%d'))

if not df_jogos.empty:
    def ligas_permitidas(row):
        # Aceita ABSOLUTAMENTE TUDO do Brasil
        if row['Pais'] == 'Brazil': return True
        
        # Filtros específicos da Europa e Mundo
        if row['Pais'] == 'England' and row['Liga'] == 'Premier League': return True
        if row['Pais'] == 'Spain' and row['Liga'] == 'La Liga': return True
        if row['Pais'] == 'Germany' and row['Liga'] == 'Bundesliga': return True
        if row['Pais'] == 'Italy' and row['Liga'] == 'Serie A': return True
        if row['Pais'] == 'France' and row['Liga'] == 'Ligue 1': return True
        
        ligas_mundiais = ['UEFA Champions League', 'UEFA Europa League', 'Copa Libertadores', 'Copa Sudamericana', 'Recopa Sudamericana', 'FIFA Club World Cup']
        return True if row['Pais'] == 'World' and row['Liga'] in ligas_mundiais else False
        
    df_jogos = df_jogos[df_jogos.apply(ligas_permitidas, axis=1)]

    if not df_jogos.empty:
        # --- FILTRO MULTISELECT REATIVADO ---
        ligas_disponiveis = sorted(df_jogos['Liga'].unique().tolist())
        ligas_sel = st.multiselect("📍 Filtrar por Liga (Lista VIP):", options=ligas_disponiveis)
        
        if ligas_sel:
            df_jogos = df_jogos[df_jogos['Liga'].isin(ligas_sel)]
        
        opcoes = df_jogos.apply(lambda x: f"[{x['Horario']}] {x['Mandante']} x {x['Visitante']} ({x['Liga']})", axis=1)
        
        if not opcoes.empty:
            jogo_sel = st.selectbox("Selecione a partida:", opcoes.tolist())
            
            if st.button("🔮 Gerar Previsão de Elite"):
                # DESCONTO DE CRÉDITO
                novo_saldo = descontar_credito(nome_user, saldo)
                st.session_state['mostrar_resultados'] = True
                st.sidebar.warning(f"Crédito utilizado! Saldo: {novo_saldo}")
                st.rerun()

            if st.session_state.get('mostrar_resultados', False):
                with st.spinner('Analisando dados...'):
                    idx = opcoes.tolist().index(jogo_sel)
                    jogo_data = df_jogos.iloc[idx]
                    
                    lambda_m = calcular_medias_ponderadas(jogo_data['ID_Mandante'], 'home')
                    lambda_v = calcular_medias_ponderadas(jogo_data['ID_Visitante'], 'away')
                    
                    st.markdown("---")
                    st.markdown("### 📋 Escalações Oficiais")
                    lineups = buscar_escalacoes(jogo_data['ID_Partida'])
                    if lineups:
                        c_esc1, c_esc2 = st.columns(2)
                        for i, time in enumerate(lineups):
                            col = c_esc1 if i == 0 else c_esc2
                            with col:
                                st.subheader(f"{time['team']['name']} ({time['formation']})")
                                st.caption(f"**Titulares:** {', '.join([p['player']['name'] for p in time['startXI']])}")
                    else:
                        st.info("🕒 Escalações oficiais 40 min antes do jogo.")

                    st.markdown("---")
                    c1, c2 = st.columns(2)
                    c1.metric(f"Força Atacante ({jogo_data['Mandante']})", f"{lambda_m:.2f}")
                    c2.metric(f"Fragilidade Defensiva ({jogo_data['Visitante']})", f"{lambda_v:.2f}")

                    p1 = px = p2 = 0
                    resultados = []
                    for i in range(6):
                        for j in range(6):
                            prob = (prob_poisson(lambda_m, i) * prob_poisson(lambda_v, j)) / 100
                            resultados.append({'Placar': f"{i} x {j}", 'Prob': prob})
                            if i > j: p1 += prob
                            elif i == j: px += prob
                            else: p2 += prob
                    
                    df_res = pd.DataFrame(resultados).sort_values(by='Prob', ascending=False)
                    st.success(f"🎯 **CRAVADA RECOMENDADA:** {df_res.iloc[0]['Placar']} ({df_res.iloc[0]['Prob']:.2f}%)")

                    st.markdown("### 💰 Calculadora de Valor (EV)")
                    od1, odx, odv = st.columns(3)
                    in_m = od1.number_input(f"Odd {jogo_data['Mandante']}", 1.0, 20.0, 2.0)
                    in_x = odx.number_input("Odd Empate", 1.0, 20.0, 3.0)
                    in_v = odv.number_input(f"Odd {jogo_data['Visitante']}", 1.0, 20.0, 3.0)

                    r1, rx, rv = st.columns(3)
                    for col, p, odd in zip([r1, rx, rv], [p1, px, p2], [in_m, in_x, in_v]):
                        ev = ((p/100) * odd) - 1
                        if ev > 0: col.success(f"✅ VALOR: +{ev:.2f}")
                        else: col.error("❌ SEM VALOR")
        else:
            st.warning("Nenhum jogo encontrado para o filtro selecionado.")
    else:
        st.warning("Nenhum jogo das Ligas VIP encontrado para hoje.")
else:
    st.info("Aguardando seleção de data...")