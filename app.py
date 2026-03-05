import streamlit as st
import requests
import pandas as pd
import math
import datetime
import pytz

# --- CONFIGURAÇÕES DA API ---
API_KEY = "c529d0695b02fa73ccdcc19cb89026d7"
HEADERS = {"x-apisports-key": API_KEY}

# --- FUNÇÕES DE DADOS COM CACHE (PROTEÇÃO DE CRÉDITOS) ---
@st.cache_data(ttl=3600) # Guarda os jogos do dia por 1 hora
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
            horario_br = data_br.strftime('%H:%M')

            dados.append({
                'ID_Partida': jogo['fixture']['id'],
                'Horario': horario_br,
                'Liga': jogo['league']['name'],
                'Pais': jogo['league']['country'], 
                'Mandante': jogo['teams']['home']['name'],
                'ID_Mandante': jogo['teams']['home']['id'],
                'Visitante': jogo['teams']['away']['name'],
                'ID_Visitante': jogo['teams']['away']['id']
            })
    return pd.DataFrame(dados)

@st.cache_data(ttl=3600) # Salva o histórico do time por 1 hora (Economia gigante)
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
        
        if local == 'home':
            gols = j['goals']['home'] if j['teams']['home']['id'] == id_time else j['goals']['away']
            if j['teams']['home']['id'] == id_time: peso += 1
        else:
            gols = j['goals']['home'] if j['teams']['away']['id'] == id_time else j['goals']['away']
            if j['teams']['away']['id'] == id_time: peso += 1
            
        for _ in range(peso):
            gols_fator.append(gols)

    return pd.Series(gols_fator).mean()

@st.cache_data(ttl=600) # Escalações atualizam mais rápido (a cada 10 min)
def buscar_escalacoes(id_partida):
    url = "https://v3.football.api-sports.io/fixtures/lineups"
    params = {"fixture": id_partida}
    response = requests.get(url, headers=HEADERS, params=params).json()
    return response.get('response', [])

def prob_poisson(media, gols):
    if media <= 0: media = 0.1
    return ((math.exp(-media) * (media ** gols)) / math.factorial(gols)) * 100

# --- INTERFACE WEB ---
st.set_page_config(page_title="FOOTBOT PRO", page_icon="⚽", layout="wide")
st.title("⚽ FOOTBOT PRO - Analista de Elite")

# 1. Seleção de Data
data_escolhida = st.date_input("Data dos jogos:", datetime.date.today(), format="DD/MM/YYYY")
df_jogos = buscar_jogos(data_escolhida.strftime('%Y-%m-%d'))

if not df_jogos.empty:
    # Filtro de Ligas VIP
    def ligas_permitidas(row):
        if row['Pais'] == 'Brazil': return True
        if row['Pais'] == 'England' and row['Liga'] == 'Premier League': return True
        if row['Pais'] == 'Spain' and row['Liga'] == 'La Liga': return True
        if row['Pais'] == 'Germany' and row['Liga'] == 'Bundesliga': return True
        if row['Pais'] == 'Italy' and row['Liga'] == 'Serie A': return True
        if row['Pais'] == 'France' and row['Liga'] == 'Ligue 1': return True
        ligas_mundiais = ['UEFA Champions League', 'UEFA Europa League', 'Copa Libertadores', 'Copa Sudamericana', 'Recopa Sudamericana', 'FIFA Club World Cup']
        return True if row['Pais'] == 'World' and row['Liga'] in ligas_mundiais else False
        
    df_jogos = df_jogos[df_jogos.apply(ligas_permitidas, axis=1)]

    if not df_jogos.empty:
        ligas_disponiveis = sorted(df_jogos['Liga'].unique().tolist())
        ligas_sel = st.multiselect("Filtrar Ligas:", options=ligas_disponiveis)
        if ligas_sel: df_jogos = df_jogos[df_jogos['Liga'].isin(ligas_sel)]
        
        opcoes = df_jogos.apply(lambda x: f"[{x['Horario']}] {x['Mandante']} x {x['Visitante']} ({x['Liga']})", axis=1)
        
        if not opcoes.empty:
            jogo_sel = st.selectbox("Selecione a partida:", opcoes.tolist())
            
            # --- CONTROLE DE ESTADO PARA NÃO SUMIR A TELA ---
            if 'ultimo_jogo' not in st.session_state:
                st.session_state['ultimo_jogo'] = jogo_sel
            
            if st.session_state['ultimo_jogo'] != jogo_sel:
                st.session_state['mostrar_resultados'] = False
                st.session_state['ultimo_jogo'] = jogo_sel

            if st.button("🔮 Gerar Previsão de Elite"):
                st.session_state['mostrar_resultados'] = True

            if st.session_state.get('mostrar_resultados', False):
                with st.spinner('Analisando dados (Usando cache se disponível)...'):
                    idx = opcoes.tolist().index(jogo_sel)
                    id_partida = df_jogos.iloc[idx]['ID_Partida']
                    id_m, id_v = df_jogos.iloc[idx]['ID_Mandante'], df_jogos.iloc[idx]['ID_Visitante']
                    nome_m, nome_v = df_jogos.iloc[idx]['Mandante'], df_jogos.iloc[idx]['Visitante']
                    
                    # Cálculos Ponderados
                    lambda_m = calcular_medias_ponderadas(id_m, local='home')
                    lambda_v = calcular_medias_ponderadas(id_v, local='away')
                    
                    st.markdown("---")
                    
                    # --- SEÇÃO DE ESCALAÇÕES ---
                    st.markdown("### 📋 Escalações Oficiais")
                    lineups = buscar_escalacoes(id_partida)
                    if lineups:
                        col_esc1, col_esc2 = st.columns(2)
                        for i, time in enumerate(lineups):
                            col = col_esc1 if i == 0 else col_esc2
                            with col:
                                st.subheader(f"{time['team']['name']} ({time['formation']})")
                                st.write(f"**Técnico:** {time['coach']['name']}")
                                titulares = [p['player']['name'] for p in time['startXI']]
                                st.caption(f"**Titulares:** {', '.join(titulares)}")
                    else:
                        st.info("🕒 Escalações oficiais disponíveis 40 min antes do jogo.")

                    st.markdown("---")
                    
                    # --- RESULTADOS E MÉTRICAS ---
                    c1, c2 = st.columns(2)
                    c1.metric(f"Força Atacante ({nome_m})", f"{lambda_m:.2f}")
                    c2.metric(f"Fragilidade Defensiva ({nome_v})", f"{lambda_v:.2f}")

                    placares = []
                    p1 = px = p2 = p_over15 = p_under25 = 0
                    for i in range(7): 
                        for j in range(7): 
                            p = (prob_poisson(lambda_m, i) * prob_poisson(lambda_v, j)) / 100
                            placares.append({'Placar': f"{i} x {j}", 'Probabilidade (%)': p})
                            if i > j: p1 += p
                            elif i == j: px += p
                            else: p2 += p
                            if (i+j) > 1.5: p_over15 += p
                            if (i+j) < 2.5: p_under25 += p
                    
                    df_res = pd.DataFrame(placares).sort_values(by='Probabilidade (%)', ascending=False)
                    
                    # INDICADOR DE CONFIANÇA
                    prob_tendencia = max(p1, px, p2)
                    st.write("### 🌡️ Nível de Confiança do Modelo")
                    st.progress(min(prob_tendencia * 2 / 100, 1.0))
                    st.write(f"Confiança no cenário mais provável: **{prob_tendencia:.1f}%**")

                    st.success(f"🎯 **CRAVADA RECOMENDADA:** **{df_res.iloc[0]['Placar']}** ({df_res.iloc[0]['Probabilidade (%)']:.2f}%)")
                    
                    st.markdown("---")

                    # --- CALCULADORA DE VALOR (EV) 3 VIAS ---
                    st.markdown("### 💰 Calculadora Tripla de Valor Esperado (EV)")
                    st.write("Digite as Odds da casa de apostas. O bot avisará qual das 3 opções tem valor matemático.")
                    
                    col_odd1, col_odd2, col_odd3 = st.columns(3)
                    odd_m = col_odd1.number_input(f"Odd: {nome_m}", min_value=1.0, value=2.0, step=0.1)
                    odd_x = col_odd2.number_input("Odd: Empate", min_value=1.0, value=3.0, step=0.1)
                    odd_v = col_odd3.number_input(f"Odd: {nome_v}", min_value=1.0, value=3.0, step=0.1)

                    # Fórmula EV: (Probabilidade * Odd) - 1
                    ev_m = ((p1 / 100) * odd_m) - 1
                    ev_x = ((px / 100) * odd_x) - 1
                    ev_v = ((p2 / 100) * odd_v) - 1

                    col_res1, col_res2, col_res3 = st.columns(3)
                    
                    with col_res1:
                        if ev_m > 0: st.success(f"✅ COM VALOR (EV: +{ev_m:.2f})\n\nOdd Justa: {(100/p1 if p1>0 else 0):.2f}")
                        else: st.error("❌ SEM VALOR")
                    
                    with col_res2:
                        if ev_x > 0: st.success(f"✅ COM VALOR (EV: +{ev_x:.2f})\n\nOdd Justa: {(100/px if px>0 else 0):.2f}")
                        else: st.error("❌ SEM VALOR")

                    with col_res3:
                        if ev_v > 0: st.success(f"✅ COM VALOR (EV: +{ev_v:.2f})\n\nOdd Justa: {(100/p2 if p2>0 else 0):.2f}")
                        else: st.error("❌ SEM VALOR")

                    st.markdown("---")
                    
                    # --- GRÁFICO E TABELA LADO A LADO ---
                    col_g, col_t = st.columns([1.2, 1])
                    with col_g:
                        st.markdown("### 📊 Top 5 Placares")
                        df_g = df_res.head(5).copy()
                        df_g['Probabilidade (%)'] = df_g['Probabilidade (%)'].round(2)
                        st.bar_chart(data=df_g, x='Placar', y='Probabilidade (%)')
                    with col_t:
                        st.markdown("### 📋 Top 10 Cenários")
                        df_t = df_res.head(10).copy()
                        df_t['Probabilidade (%)'] = df_t['Probabilidade (%)'].apply(lambda x: f"{x:.2f}%")
                        st.dataframe(df_t, hide_index=True, use_container_width=True)
        else:
            st.warning("Selecione um campeonato no filtro acima para listar os jogos.")
    else:
        st.warning("Nenhum jogo das Ligas VIP encontrado para hoje.")
else:
    st.info("Aguardando seleção de data...")