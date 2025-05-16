# treinar_classificadores.py
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report, ConfusionMatrixDisplay
import matplotlib.pyplot as plt # Para exibir a matriz de confusão
import joblib
import os
import re
import nltk
from nltk.corpus import stopwords
# from nltk.stem import RSLPStemmer # Stemmer para português (opcional)

# --- Download de recursos NLTK (stopwords) ---
try:
    nltk.data.find('corpora/stopwords')
except LookupError: # CORRIGIDO para LookupError
    print("Baixando recurso 'stopwords' do NLTK...")
    nltk.download('stopwords', quiet=True) # Adicionado quiet=True para menos verbosidade
# try: # Se for usar o RSLPStemmer
#     nltk.data.find('stemmers/rslp')
# except LookupError:
#     print("Baixando recurso 'rslp' do NLTK...")
#     nltk.download('rslp')

# --- Configurações ---
MODEL_OUTPUT_DIR = "models"
MODEL_AREA_DIREITO_FILENAME = "classificador_area_direito.joblib"
MODEL_TIPO_TAREFA_FILENAME = "classificador_tipo_tarefa.joblib"

# Lista de stopwords em português do NLTK
portuguese_stopwords = stopwords.words('portuguese')
# Adicionar palavras comuns em perguntas que podem não ser úteis para classificação
palavras_extras_irrelevantes = ['quais', 'qual', 'como', 'fazer', 'posso', 'gostaria', 'saber', 'sobre', 
                                'direito', 'lei', 'artigo', 'processo', 'gostaria', 'poderia', 'ajuda',
                                'dúvida', 'informação', 'explicar', 'seria']
portuguese_stopwords.extend(palavras_extras_irrelevantes)

# stemmer = RSLPStemmer() # Inicialize se for usar

def preprocess_text(text):
    if not isinstance(text, str):
        return ""
    text = text.lower() # Minúsculas
    text = re.sub(r'[^\w\s]', '', text) # Remove pontuação
    text = re.sub(r'\d+', '', text) # Remove números (opcional)
    tokens = text.split()
    # Remove stopwords. Stemming é opcional e pode ser agressivo para termos jurídicos.
    # Lematização seria melhor, mas é mais complexa de implementar sem bibliotecas adicionais como Spacy.
    # tokens = [stemmer.stem(word) for word in tokens if word not in portuguese_stopwords and len(word) > 2]
    tokens = [word for word in tokens if word not in portuguese_stopwords and len(word) > 2]
    return " ".join(tokens)

def carregar_dados_de_csv(caminho_csv, coluna_texto='texto', coluna_label='label'):
    """Carrega dados de um arquivo CSV."""
    try:
        df = pd.read_csv(caminho_csv)
        if coluna_texto not in df.columns or coluna_label not in df.columns:
            raise ValueError(f"CSV deve conter as colunas '{coluna_texto}' e '{coluna_label}'")
        print(f"Dados carregados de {caminho_csv}: {len(df)} amostras.")
        # Remove linhas onde o texto ou o label estão vazios
        df.dropna(subset=[coluna_texto, coluna_label], inplace=True)
        df = df[df[coluna_texto].str.strip() != '']
        df = df[df[coluna_label].str.strip() != '']
        print(f"Amostras válidas após limpeza: {len(df)}")
        return df
    except FileNotFoundError:
        print(f"ERRO: Arquivo CSV não encontrado em '{caminho_csv}'. Crie este arquivo com seus dados de treinamento.")
        return pd.DataFrame(columns=[coluna_texto, coluna_label]) # Retorna DataFrame vazio
    except Exception as e:
        print(f"ERRO ao carregar dados de {caminho_csv}: {e}")
        return pd.DataFrame(columns=[coluna_texto, coluna_label])

def treinar_e_avaliar_modelo(df: pd.DataFrame, text_column: str, label_column: str, model_filename: str):
    print(f"\n--- Treinando Modelo para '{label_column}': {model_filename} ---")
    
    if df.empty or len(df) < 10: # Adicionado um limite mínimo de amostras
        print(f"Dados insuficientes para treinar o modelo '{model_filename}'. São necessárias mais amostras.")
        return None

    df['texto_processado'] = df[text_column].apply(preprocess_text)
    
    # Verifica se há dados após o pré-processamento
    df_processado = df[df['texto_processado'].str.strip() != '']
    if df_processado.empty or len(df_processado) < 10:
        print(f"Dados insuficientes após pré-processamento para '{model_filename}'.")
        return None
    
    print(f"Distribuição das classes para '{label_column}':\n{df_processado[label_column].value_counts()}")

    # Verifica se há pelo menos 2 amostras por classe para estratificação e se há pelo menos 2 classes
    class_counts = df_processado[label_column].value_counts()
    if len(class_counts) < 2:
        print(f"ERRO: São necessárias pelo menos 2 classes distintas para treinar o classificador '{model_filename}'. Encontrado: {len(class_counts)}.")
        return None
    
    stratify_data = None
    if not (class_counts < 2).any(): # Se todas as classes têm pelo menos 2 amostras
        stratify_data = df_processado[label_column]
    else:
        print(f"AVISO: Algumas classes em '{label_column}' têm menos de 2 amostras. A estratificação pode não ser ideal ou falhar.")

    try:
        X_train, X_test, y_train, y_test = train_test_split(
            df_processado['texto_processado'], df_processado[label_column],
            test_size=0.25, random_state=42, stratify=stratify_data
        )
    except ValueError as e_split:
        print(f"AVISO: Erro ao dividir dados com estratificação para '{model_filename}' (detalhes: {e_split}). Tentando sem estratificação.")
        X_train, X_test, y_train, y_test = train_test_split(
            df_processado['texto_processado'], df_processado[label_column],
            test_size=0.25, random_state=42
        )

    if len(X_train) == 0 or len(X_test) == 0:
        print(f"Divisão resultou em conjuntos de treino ou teste vazios para '{model_filename}'. Verifique seus dados.")
        return None

    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(ngram_range=(1, 2), max_df=0.90, min_df=2)), # min_df=2 ajuda a ignorar termos muito raros
        ('clf', LogisticRegression(solver='liblinear', C=1.0, random_state=42, class_weight='balanced'))
    ])

    try:
        pipeline.fit(X_train, y_train)
    except ValueError as e_fit: # Ex: se o vocabulário estiver vazio após TF-IDF
        print(f"ERRO ao treinar o pipeline para '{model_filename}': {e_fit}")
        return None

    print(f"\nAvaliação do Modelo: {model_filename} (no conjunto de teste)")
    y_pred = pipeline.predict(X_test)
    
    # Garante que todos os labels estejam presentes para o classification_report
    unique_labels = sorted(list(set(y_train) | set(y_test)))
    print(classification_report(y_test, y_pred, labels=unique_labels, zero_division=0))

    # Matriz de Confusão (opcional, mas útil)
    # try:
    #     print("\nMatriz de Confusão:")
    #     cm_display = ConfusionMatrixDisplay.from_predictions(y_test, y_pred, labels=unique_labels, xticks_rotation='vertical')
    #     plt.title(f"Matriz de Confusão - {model_filename}")
    #     plt.show() # Isso pode não funcionar bem se rodado em um ambiente sem GUI
    #     # Para salvar: cm_display.figure_.savefig(f"{model_filename}_confusion_matrix.png")
    # except Exception as e_cm:
    #     print(f"Não foi possível gerar a matriz de confusão visual: {e_cm}")


    # Salvar o modelo
    if not os.path.exists(MODEL_OUTPUT_DIR):
        os.makedirs(MODEL_OUTPUT_DIR)
    path_modelo = os.path.join(MODEL_OUTPUT_DIR, model_filename)
    joblib.dump(pipeline, path_modelo)
    print(f"Modelo '{model_filename}' salvo em: {path_modelo}")
    return pipeline

# --- PONTO DE ENTRADA DO SCRIPT ---
if __name__ == '__main__':
    print("Iniciando o script de treinamento dos classificadores...")

    # --- Classificador de Área do Direito ---
    # CRIE UM ARQUIVO CSV chamado 'dados_area_direito.csv' na mesma pasta deste script
    # com as colunas 'texto' e 'area'
    df_area = carregar_dados_de_csv("dados_area_direito.csv", coluna_texto='texto', coluna_label='area')
    if not df_area.empty:
        modelo_area_treinado = treinar_e_avaliar_modelo(
            df_area,
            text_column='texto',
            label_column='area',
            model_filename=MODEL_AREA_DIREITO_FILENAME
        )
        if modelo_area_treinado:
            print("\nTeste rápido do modelo de ÁREA treinado:")
            test_query_area = preprocess_text("quais os meus direitos numa demissão?")
            print(f"'{test_query_area}' -> Área: {modelo_area_treinado.predict([test_query_area])[0]}")


    # --- Classificador de Tipo de Tarefa ---
    # CRIE UM ARQUIVO CSV chamado 'dados_tipo_tarefa.csv' na mesma pasta
    # com as colunas 'texto' e 'tarefa'
    df_tarefa = carregar_dados_de_csv("dados_tipo_tarefa.csv", coluna_texto='texto', coluna_label='tarefa')
    if not df_tarefa.empty:
        modelo_tarefa_treinado = treinar_e_avaliar_modelo(
            df_tarefa,
            text_column='texto',
            label_column='tarefa',
            model_filename=MODEL_TIPO_TAREFA_FILENAME
        )
        if modelo_tarefa_treinado:
            print("\nTeste rápido do modelo de TAREFA treinado:")
            test_query_tarefa = preprocess_text("resuma este contrato por favor")
            print(f"'{test_query_tarefa}' -> Tarefa: {modelo_tarefa_treinado.predict([test_query_tarefa])[0]}")


    print(f"\nScript de treinamento concluído. Verifique a pasta '{MODEL_OUTPUT_DIR}'.")