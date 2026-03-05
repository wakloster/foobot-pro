import requests
import pandas as pd
import math

API_KEY = "c529d0695b02fa73ccdcc19cb89026d7"
HEADERS = {"x-apisports-key": API_KEY}

def calcular_medias(id_time):
    url = "https://v3.football.api-sports.io/fixtures"
    # Pegamos os últimos 10 jogos finalizados ('status': 'FT')
    params = {"team": id_time, "last": "10", "status": "FT"} 
    
    response = requests.get(url, headers=HEADERS, params=params).json()
    jogos = response.get('response', [])
    
    gols_feitos = []
    gols_sofridos = []
    
    for j in jogos:
        if j['teams']['home']['id'] == id_time:
            gols_feitos.append(j['goals']['home'])
            gols_sofridos.append(j['goals']['away'])
        else:
            gols_feitos.append(j['goals']['away'])
            gols_sofridos.append(j['goals']['home'])
            
    # Se não houver histórico, retornamos 0.1 para não quebrar o cálculo matemático
    if not gols_feitos:
        return 0.1, 0.1
        
    return pd.Series(gols_feitos).mean(), pd.Series(gols_sofridos).mean()

def probabilidade_poisson(media_gols, gols_alvo):
    # Aplicação da fórmula Matemática de Poisson
    return ((math.exp(-media_gols) * (media_gols ** gols_alvo)) / math.factorial(gols_alvo)) * 100

# Vamos usar os IDs da sua tabela (Linha 1: Mutondo Stars x ZESCO United)
id_mandante = 21875
id_visitante = 5214

print("Buscando histórico na API e processando dados...\n")

# 1. Calculamos o histórico
gols_m, sofridos_m = calcular_medias(id_mandante)
gols_v, sofridos_v = calcular_medias(id_visitante)

# 2. Calculamos o "Lambda" (Força de ataque vs Fraqueza da defesa)
lambda_mandante = (gols_m + sofridos_v) / 2
lambda_visitante = (gols_v + sofridos_m) / 2

print(f"Expectativa de Gols do Mandante: {lambda_mandante:.2f}")
print(f"Expectativa de Gols do Visitante: {lambda_visitante:.2f}")
print("-" * 30)
print("PROBABILIDADES DE PLACAR EXATO (Até 2 gols):")

# 3. Geramos as probabilidades dos placares
for gols_m in range(3):
    for gols_v in range(3):
        prob_m = probabilidade_poisson(lambda_mandante, gols_m)
        prob_v = probabilidade_poisson(lambda_visitante, gols_v)
        
        # A probabilidade do placar exato é a multiplicação das duas chances
        prob_placar = (prob_m * prob_v) / 100
        print(f"Placar {gols_m} x {gols_v}: {prob_placar:.2f}%")