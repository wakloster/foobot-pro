import requests
import pandas as pd
from datetime import datetime

# Sua chave oficial
API_KEY = "c529d0695b02fa73ccdcc19cb89026d7"
HEADERS = {"x-apisports-key": API_KEY}

def buscar_jogos_por_data(data_jogo):
    """
    Busca todas as partidas de uma data específica.
    Formato esperado da data: 'YYYY-MM-DD'
    """
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"date": data_jogo}
    
    print(f"Buscando jogos para o dia {data_jogo}...")
    response = requests.get(url, headers=HEADERS, params=params).json()
    
    # Validação caso a API retorne erro ou limite excedido
    if 'response' not in response or not response['response']:
        print("Nenhum jogo encontrado ou erro na API.")
        return pd.DataFrame()

    jogos_brutos = response['response']
    dados_limpos = []

    for jogo in jogos_brutos:
        # Filtrando apenas partidas que ainda não aconteceram ('NS' = Not Started)
        if jogo['fixture']['status']['short'] == 'NS':
            dados_limpos.append({
                'ID_Partida': jogo['fixture']['id'],
                'Liga': jogo['league']['name'],
                'ID_Mandante': jogo['teams']['home']['id'],
                'Mandante': jogo['teams']['home']['name'],
                'ID_Visitante': jogo['teams']['away']['id'],
                'Visitante': jogo['teams']['away']['name']
            })

    df_jogos = pd.DataFrame(dados_limpos)
    return df_jogos

# Testando o script com a data de hoje
data_hoje = datetime.today().strftime('%Y-%m-%d')
df_agenda = buscar_jogos_por_data(data_hoje)

print("\n--- Próximos Jogos Disponíveis ---")
# Exibindo os 10 primeiros para não poluir muito a tela
print(df_agenda.head(10))
