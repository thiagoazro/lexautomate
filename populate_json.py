# populate_db.py
import json
import os
from dotenv import load_dotenv
from db_utils import inserir_modelo_peca, get_modelos_collection # Importe get_modelos_collection para limpeza

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv() 

def populate_models_from_json(json_file_path="modelos_pecas.json"):
    """
    Lê os modelos de peças de um arquivo JSON e os insere no MongoDB.
    """
    try:
        with open(json_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        print(f"Lendo modelos do arquivo: {json_file_path}")
        
        # Opcional: Esvaziar a coleção antes de popular para evitar duplicatas em novas execuções.
        # ISSO VAI APAGAR TODOS OS DADOS DA SUA COLEÇÃO! Use com cautela.
        modelos_collection = get_modelos_collection()
        if modelos_collection is not None:
            print("INFO: Limpando a coleção antes de popular (OPCIONAL - COMENTE SE NÃO QUISER LIMPAR!)...")
            # modelos_collection.delete_many({}) # <--- Descomente esta linha para limpar a coleção
            print("INFO: Coleção limpa (se a linha acima estiver descomentada).")
        else:
            print("AVISO: Não foi possível obter a coleção para limpeza. Verifique sua conexão com o MongoDB.")
            # Se a conexão falhou aqui, não adianta tentar inserir
            return 

        # Itera sobre a estrutura aninhada do JSON para inserir cada modelo individualmente
        total_modelos_processados = 0
        for area, tipos in data.items():
            for tipo_peca, modelos in tipos.items():
                for nome_modelo, info in modelos.items():
                    prompt_template = info.get("prompt_template", "")
                    reivindicacoes_comuns = info.get("reivindicacoes_comuns", [])
                    descricao = info.get("descricao", "") # Pega a descrição se existir no JSON

                    print(f"Processando: {nome_modelo} ({area} - {tipo_peca})")
                    
                    # Chama a função de inserção/atualização do db_utils
                    if inserir_modelo_peca(area, tipo_peca, nome_modelo, prompt_template, reivindicacoes_comuns, descricao):
                        total_modelos_processados += 1
                        print(f"  -> Sucesso!")
                    else:
                        print(f"  -> Falha. Verifique os logs de erro acima para detalhes.")
        
        print(f"\nPopulação do banco de dados concluída. Total de modelos processados: {total_modelos_processados}.")

    except FileNotFoundError:
        print(f"ERRO: Arquivo JSON '{json_file_path}' não encontrado. Certifique-se de que ele existe na raiz do projeto.")
    except json.JSONDecodeError as e:
        print(f"ERRO: Erro ao decodificar JSON do arquivo '{json_file_path}': {e}. Verifique a sintaxe do JSON.")
    except Exception as e:
        print(f"ERRO geral ao popular o banco de dados: {e}")
        import traceback
        traceback.print_exc() # Imprime o stack trace completo para depuração

if __name__ == "__main__":
    populate_models_from_json()