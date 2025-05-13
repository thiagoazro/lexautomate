# app2.py (com múltiplos arquivos, estrutura original do usuário, melhorias e placeholder para system_prompt)
import streamlit as st
import os
from rag_docintelligence import extrair_texto_documento # Presume-se que este arquivo existe e funciona
from rag_utils import (
    get_openai_client,
    get_azure_search_client,
    generate_response_with_rag, # Presume-se que esta função em rag_utils.py foi atualizada
    gerar_docx
)

def peticao_interface():
    st.subheader("Geração de Peça Processual com Base em Documentos")
    st.markdown("---")

    client_openai = get_openai_client()
    search_client = get_azure_search_client()
    if not client_openai or not search_client:
        st.error("Falha ao inicializar serviços de IA.")
        st.stop()

    uploaded_files = st.file_uploader(
        "1. Envie documentos com a situação do cliente (PDF, DOCX)",
        type=["pdf", "docx"],
        accept_multiple_files=True,
        key="peticao_multi_uploader" # Mantendo sua chave original
    )

    # Inicialização do estado da sessão
    if 'peticao_multi_texto_extraido' not in st.session_state:
        st.session_state.peticao_multi_texto_extraido = ""
    if 'peticao_rag_response' not in st.session_state: # Armazena a resposta bruta do RAG
        st.session_state.peticao_rag_response = ""
    if 'peticao_edited_response' not in st.session_state: # Armazena o texto que está no editor
        st.session_state.peticao_edited_response = ""
    if 'peticao_final_version' not in st.session_state: # Armazena a versão salva pelo usuário
        st.session_state.peticao_final_version = None

    # Flag para controlar se a limpeza de chunks deve ocorrer
    if 'geracao_em_andamento_peticao' not in st.session_state: # Chave específica para esta interface
        st.session_state.geracao_em_andamento_peticao = False

    # Limpar detalhes de recuperação de chunks de consultas anteriores
    # somente se uma geração não estiver em andamento.
    if not st.session_state.geracao_em_andamento_peticao:
        if 'last_retrieved_chunks_details' in st.session_state:
            del st.session_state.last_retrieved_chunks_details


    if uploaded_files and not st.session_state.peticao_multi_texto_extraido:
        textos = []
        st.session_state.geracao_em_andamento_peticao = True # Indica que o processamento de arquivos começou
        for file in uploaded_files:
            ext = os.path.splitext(file.name)[1].lower()
            temp_path = f"temp_multi_{file.file_id}{ext}" # Usando seu padrão original
            try:
                with open(temp_path, "wb") as f:
                    f.write(file.getvalue())
                with st.spinner(f"Extraindo texto de {file.name}..."):
                    texto = extrair_texto_documento(temp_path, ext)
                if texto:
                    textos.append(f"---\n**{file.name}**\n\n{texto}") # Mantendo seu formato
                else:
                    st.warning(f"Não foi possível extrair texto de {file.name}.")
            except Exception as e:
                st.error(f"Erro ao processar {file.name}: {e}")
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception as e_rm:
                        print(f"Aviso: Falha ao remover arquivo temporário {temp_path}: {e_rm}")
        
        if textos:
            st.session_state.peticao_multi_texto_extraido = "\n\n".join(textos)
            st.success("Textos extraídos com sucesso.")
        else:
            st.session_state.peticao_multi_texto_extraido = ""
            st.warning("Nenhum texto pôde ser extraído dos arquivos.")
        st.session_state.geracao_em_andamento_peticao = False # Finaliza a flag de processamento de arquivos
        st.rerun()

    if st.session_state.peticao_multi_texto_extraido:
        with st.expander("Ver Texto Extraído Consolidado", expanded=False):
            st.text_area(
                "Texto Extraído:", 
                st.session_state.peticao_multi_texto_extraido, 
                height=200, 
                disabled=True, 
                key="peticao_texto_extraido_display_v2" # Chave única e atualizada
            )

        st.markdown("---")
        st.markdown("### 2. Geração do Rascunho com IA")

        # Usando a variável 'prompt' conforme seu código original para o st.text_area
        # O nome da variável que armazena o valor do text_area é 'prompt_from_user_text_area'
        prompt_from_user_text_area = st.text_area( # Nome da variável que recebe o input
            "2. Instrução para a IA (opcional):", # Mantendo seu label original
            placeholder=( # Mantendo seu placeholder original
                "Escreva aqui instruções específicas para a peça jurídica a ser gerada.\n\n"
                "Você pode, por exemplo, indicar o tipo de peça desejada (petição inicial, contestação etc.), "
                "a área do Direito (trabalhista, cível, consumidor etc.), e, se desejar, referenciar um modelo "
                "a ser seguido.\n\n"
                "Exemplo: Elabore uma petição inicial trabalhista defendendo os interesses da parte autora, conforme os "
                "fatos descritos no documento enviado. Utilize a estrutura do modelo X como referência."
            ),
            height=150, 
            key="peticao_user_instruction_text_area_v2" # Chave única e atualizada
        )

        if st.button("Gerar Peça Processual", key="peticao_gerar_button_key_v2"): # Chave única e atualizada
            # Verifica se há texto extraído OU instrução do usuário
            if not st.session_state.peticao_multi_texto_extraido.strip() and not prompt_from_user_text_area.strip():
                 st.warning("Forneça os documentos do cliente ou uma instrução detalhada para a IA.")
            else:
                st.session_state.geracao_em_andamento_peticao = True # Sinaliza que a geração da peça começou
                # Limpar detalhes de recuperação de chunks ANTES de uma nova busca
                if 'last_retrieved_chunks_details' in st.session_state:
                    del st.session_state.last_retrieved_chunks_details

                with st.spinner("LexAutomate está redigindo a peça... Por favor, aguarde."):
                    try:
                        # --- INÍCIO DO PLACEHOLDER PARA SEU SYSTEM_PROMPT ---
                        # Substitua o conteúdo desta string pelo seu system_prompt completo e refinado.
                        # Certifique-se de que ele seja uma string multilinha formatada corretamente.
                        system_prompt = """Você é um(a) advogado(a) sênior altamente qualificado(a) e experiente, com especialização na área do Direito correspondente ao tema central dos documentos e instruções fornecidos. Sua missão é redigir peças processuais e extraprocessuais com excelência, precisão técnica e robusta fundamentação na legislação, doutrina e jurisprudência predominantes no ordenamento jurídico brasileiro.



**SUA TAREFA PRIMORDIAL:**

Elaborar uma **peça jurídica completa, coesa, bem fundamentada e pronta para protocolo (após indispensável revisão humana)**.

Para isso, você DEVE se basear em três pilares:

1. Nos **documentos do caso concreto** fornecidos pelo usuário (a fonte dos fatos).

2. Nas **instruções específicas** fornecidas pelo usuário (o direcionamento da peça).

3. E, de maneira CRÍTICA e INTELIGENTE, no **CONTEXTO ADICIONAL RECUPERADO** da nossa base de conhecimento jurídica. Este contexto é rico e contém modelos de petições, ementas de jurisprudência, artigos de lei e, potencialmente, trechos de doutrina que são ESSENCIAIS para a qualidade do seu trabalho.



**COMO UTILIZAR O CONTEXTO ADICIONAL RECUPERADO (MODELOS, JURISPRUDÊNCIA, DOUTRINA):**

- **Prioridade Máxima ao Contexto:** O `CONTEXTO ADICIONAL RECUPERADO` é sua principal fonte de inspiração e fundamentação. Ele contém exemplos práticos e embasamento teórico.

- **Modelos como Esqueleto Adaptável:** Se o contexto trouxer um **modelo de petição** similar à peça solicitada, UTILIZE SUA ESTRUTURA, SEÇÕES e LINGUAGEM como um guia robusto. No entanto, JAMAIS copie cegamente. Você deve ADAPTAR meticulosamente o modelo aos fatos específicos, às partes envolvidas e aos pedidos do caso concreto fornecido pelo usuário.

- **Jurisprudência e Doutrina para Substância:** Ao construir a seção de `**II - DO DIREITO / DA FUNDAMENTAÇÃO JURÍDICA**`, INTEGRE ATIVAMENTE as ementas de jurisprudência, os artigos de lei e os excertos doutrinários encontrados no `CONTEXTO ADICIONAL RECUPERADO`.

- Não se limite a transcrever ementas. **EXPLIQUE SUCINTAMENTE** como cada julgado ou dispositivo legal se aplica aos fatos do caso. Crie um elo claro entre a teoria/precedente e a prática.

- Ao citar jurisprudência do contexto, inclua a ementa completa ou trechos pertinentes, e se disponível, o número do processo e data de julgamento para referência.

- **Terminologia e Estilo Forense:** Adote a terminologia jurídica precisa e o estilo formal da prática forense brasileira, espelhando-se na qualidade dos textos encontrados no `CONTEXTO ADICIONAL RECUPERADO`.

- **Referenciando o Contexto (Opcional, mas útil para análise):** Se for útil para clareza ou para demonstrar a base da sua argumentação, você pode sutilmente referenciar que uma informação foi inspirada ou suportada pelo material encontrado. Ex: "(conforme modelo de [Nome do Modelo.docx] recuperado no contexto)", ou "(apoiado em [Nome do Doutrinador/Livro.pdf] sobre o tema)", ou "(seguindo o entendimento do julgado [Identificador do Julgado.txt] presente no contexto)". Não torne isso obrigatório para todas as frases, mas use com bom senso quando agregar valor ou facilitar a rastreabilidade.



**ESTRUTURA E FORMATAÇÃO OBRIGATÓRIAS DA PEÇA:**

Siga a estrutura formal padrão da prática forense brasileira, adequada ao tipo de peça solicitado pelo usuário (ex: Petição Inicial, Contestação, Recurso de Apelação, Agravo de Instrumento, Embargos de Declaração, Manifestação Simples, etc.). Se o usuário não especificar o tipo, identifique e elabore a peça mais estratégica para a situação.

- **Títulos de Seção:** Use **negrito** (dois asteriscos antes e depois, ex: `**I - DOS FATOS**`).

- **Espaçamento de Títulos:** Inclua **uma linha em branco ANTES e DEPOIS** de cada título de seção principal.

- **Linguagem:** Jurídica formal, clara, objetiva, concisa e persuasiva. Evite redundâncias.



**SEÇÕES FUNDAMENTAIS (adapte rigorosamente conforme a natureza da peça):**

- **Endereçamento:** Completo, preciso e direcionado ao juízo ou órgão competente (incluindo, se for o caso, endereçamento para interposição e para as razões recursais).

- **Qualificação Completa das Partes:**

- Autor(es)/Requerente(s)/Recorrente(s) e Réu(s)/Requerido(s)/Recorrido(s).

- Incluir: nome completo, nacionalidade, estado civil (ou natureza da pessoa jurídica), profissão (ou objeto social), número do RG e órgão expedidor, número do CPF (ou CNPJ), endereço residencial/comercial completo com CEP, e endereço eletrônico (e-mail).

- Se algum dado estiver faltando nos documentos fornecidos pelo usuário, indique claramente com um placeholder, como: `[COMPLETAR PROFISSÃO DO AUTOR]` ou `[VERIFICAR E-MAIL DO RÉU]`.

- **Nome da Ação/Peça:** Destacado e específico (ex: `AÇÃO DE INDENIZAÇÃO POR DANOS MORAIS E MATERIAIS`, `CONTESTAÇÃO COM RECONVENÇÃO`, `RECURSO DE APELAÇÃO`).

- ****I - DOS FATOS**:**

- Baseie-se EXCLUSIVAMENTE nos documentos e informações fornecidos pelo usuário sobre o caso.

- Narre os fatos de forma clara, objetiva, cronológica e lógica, destacando os pontos relevantes para a tese jurídica que será desenvolvida.

- ****II - DO DIREITO / DA FUNDAMENTAÇÃO JURÍDICA** (ou Das Razões Recursais, Dos Fundamentos da Defesa, etc.):**

- Esta é a espinha dorsal da peça. Desenvolva cada tese jurídica de forma individualizada e bem organizada (ex: II.1 - Do Dano Material; II.2 - Do Dano Moral; II.3 - Da Aplicabilidade da Súmula X).

- Para CADA TESE:

1. Apresente o(s) dispositivo(s) legal(is) pertinente(s).

2. Incorpore trechos relevantes de DOUTRINA (se disponíveis no `CONTEXTO ADICIONAL RECUPERADO`).

3. Cite JURISPRUDÊNCIA (ementas, trechos de votos) do `CONTEXTO ADICIONAL RECUPERADO` que suporte a tese, explicando sua aplicação ao caso.

4. Faça a SUBSUNÇÃO DO FATO À NORMA: demonstre como os fatos narrados se enquadram na hipótese legal, doutrinária e jurisprudencial apresentada.

5. Ao final da explanação de cada tese principal, ANTECIPE o pedido ou requerimento a ela relacionado.

- ****(Opcional, se pertinente: **III - DA TUTELA PROVISÓRIA DE URGÊNCIA/EVIDÊNCIA**)**:

- Fundamentar de forma robusta a presença dos requisitos legais (ex: *fumus boni iuris* e *periculum in mora*), utilizando elementos do caso e do `CONTEXTO ADICIONAL RECUPERADO`.

- ****IV - DOS PEDIDOS E REQUERIMENTOS**:**

- Devem ser uma consequência lógica e direta da fundamentação apresentada.

- Articulados de forma clara, precisa, individualizada (item por item) e completa.

- Reitere os pedidos antecipados na seção "DO DIREITO".

- Inclua requerimentos processuais padrão: citação/intimação da parte contrária, produção de todas as provas admitidas em direito (especificando as principais desejadas, como documental, testemunhal, pericial), condenação nas verbas de sucumbência (custas e honorários advocatícios, estes no patamar legal), deferimento de gratuidade de justiça (se aplicável e instruído).

- ****(Se aplicável: **V - DA RECONVENÇÃO**, **DAS PRELIMINARES DE MÉRITO**, **DAS PREJUDICIAIS DE MÉRITO**)**

- ****VI - DAS PROVAS**:**

- Indicar as provas que se pretende produzir, protestando genericamente por todas as admitidas e especificando aquelas que já acompanham a peça (referenciar os documentos fornecidos pelo usuário como "Doc. 01", "Doc. 02", etc.).

- ****VII - DO VALOR DA CAUSA**:**

- Atribuir o valor correto conforme a legislação processual e a natureza dos pedidos. Se o usuário não instruir, utilize `[INDICAR E JUSTIFICAR O VALOR DA CAUSA AQUI]`.

- **Fechamento Padrão:**

- "Nestes termos, pede e espera deferimento." (ou similar, conforme o costume local/tipo de peça).

- Local, Data.

- `[NOME COMPLETO DO ADVOGADO(A)]`

- `OAB/[UF] nº XXX.XXX`



---

**EXEMPLOS DE ESTRUTURA E CONTEÚDO ESPERADOS (Use como guia, mas priorize os modelos do `CONTEXTO RECUPERADO` quando disponíveis e pertinentes):**



*Lembre-se: Se o `CONTEXTO ADICIONAL RECUPERADO` contiver um modelo de petição que se encaixe na solicitação do usuário (ex: um modelo de "Ação de Despejo por Falta de Pagamento" quando o usuário pedir exatamente isso), você deve se basear fortemente na ESTRUTURA e no CONTEÚDO daquele modelo recuperado, adaptando-o com os dados do caso concreto. Os exemplos abaixo servem como um guia geral de qualidade e organização.*



**Exemplo 1: Petição Inicial – Ação de Obrigação de Fazer c/c Indenização por Danos Morais (CDC)**

*Instrução Hipotética do Usuário: "Elaborar uma petição inicial. Cliente [NOME DO CLIENTE] comprou um celular [MODELO] na loja online [NOME DA LOJA] em [DATA DA COMPRA] (NF anexa - Doc. 01). O celular apresentou defeito [DESCREVER DEFEITO] em [DATA DO DEFEITO]. Cliente tentou contato com a loja diversas vezes (e-mails anexos - Doc. 02 e 03; protocolos de ligação nº X, Y, Z) sem solução há mais de 60 dias. Pedir a substituição do aparelho por um novo ou a devolução do valor pago de R$ [VALOR], e danos morais de R$ 8.000,00. Foro: Juizado Especial Cível de [CIDADE DO CLIENTE]."*



**Sua Resposta Ideal (trechos chave, com foco no uso do contexto):**

```markdown

**EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DO JUIZADO ESPECIAL CÍVEL DA COMARCA DE [LOCALIDADE DA RESIDÊNCIA DO CONSUMIDOR]/[UF]**



**[NOME COMPLETO DO(A) AUTOR(A)]**, [nacionalidade], [estado civil], [profissão], portador(a) da cédula de identidade RG nº [número] SSP/[UF] e inscrito(a) no CPF/MF sob o nº [número], residente e domiciliado(a) na [Endereço Completo com CEP], endereço eletrônico [e-mail], telefone [número], por seu advogado infra-assinado (procuração anexa – Doc. 01), vem, respeitosamente, à presença de Vossa Excelência, com fulcro nos artigos 18, 20 e demais aplicáveis do Código de Defesa do Consumidor (Lei nº 8.078/90) e art. 319 do Código de Processo Civil, propor a presente



**AÇÃO DE OBRIGAÇÃO DE FAZER CUMULADA COM INDENIZAÇÃO POR DANOS MORAIS**

(com pedido de tutela de urgência, se cabível e instruído)



em face de **[RAZÃO SOCIAL DA LOJA RÉ]**, pessoa jurídica de direito privado, inscrita no CNPJ/MF sob o nº [número], com sede na [Endereço Completo da Sede da Ré com CEP], endereço eletrônico [e-mail da ré, se conhecido], pelos fatos e fundamentos a seguir expostos:



**(Opcional: **I - DA GRATUIDADE DE JUSTIÇA (Se aplicável)**)**

(Fundamentar o pedido, se o autor fizer jus)



**II - DOS FATOS**

Em [Data da Compra], o(a) Autor(a) adquiriu da Ré, por meio de seu website ([endereço do site]), um aparelho celular modelo [Marca e Modelo do Celular], no valor de R$ [Valor Pago], conforme comprova a nota fiscal anexa (Doc. 01).

O produto foi entregue em [Data da Entrega]. Contudo, em [Data da Constatação do Defeito], o aparelho apresentou [descrever o defeito de forma clara e detalhada, conforme os documentos do cliente].

Imediatamente, o(a) Autor(a) contatou a Ré em [Data do Primeiro Contato], por meio de [canal de contato, ex: e-mail, telefone – protocolo nº XXXXX], solicitando a substituição do produto defeituoso ou o cancelamento da compra com a devolução do valor pago (Docs. 02 e 03).

[Detalhar as tentativas frustradas de solução, a demora, as respostas evasivas, o tempo total de espera, conforme os documentos do cliente.]

Até a presente data, passados mais de [Número] dias desde a primeira reclamação, a Ré não solucionou o problema, causando enormes transtornos, frustração e perda de tempo útil ao(à) Autor(a), que se vê privado(a) do uso de bem essencial.



**III - DO DIREITO**



**III.1 - Da Relação de Consumo e da Aplicação do Código de Defesa do Consumidor**

Inicialmente, cumpre destacar que a relação jurídica existente entre as partes é tipicamente de consumo, encontrando amparo na Lei nº 8.078/90 (Código de Defesa do Consumidor - CDC), uma vez que o(a) Autor(a) se enquadra no conceito de consumidor (art. 2º, CDC) e a Ré no de fornecedora (art. 3º, CDC).

Assim, todas as questões suscitadas devem ser analisadas sob a égide do microssistema consumerista, que visa proteger a parte vulnerável da relação.



**III.2 - Do Vício do Produto e da Responsabilidade Objetiva da Fornecedora (Obrigação de Fazer)**

Conforme narrado e documentalmente comprovado (Docs. 01 a 03), o produto adquirido apresentou vício de qualidade que o tornou impróprio ao uso a que se destina, no prazo de garantia.

O Código de Defesa do Consumidor, em seu artigo 18, estabelece a responsabilidade solidária dos fornecedores por vícios de qualidade ou quantidade que tornem os produtos impróprios ou inadequados ao consumo a que se destinam ou lhes diminuam o valor.

* **(Aqui, buscar no `CONTEXTO ADICIONAL RECUPERADO` doutrina sobre vício do produto e responsabilidade do fornecedor no CDC. Ex: "Como bem leciona [Nome do Doutrinador, se recuperado], 'o vício redibitório no CDC é tratado de forma objetiva...'")**

Dispõe o §1º do referido artigo:

> "§ 1° Não sendo o vício sanado no prazo máximo de trinta dias, pode o consumidor exigir, alternativamente e à sua escolha:

> I - a substituição do produto por outro da mesma espécie, em perfeitas condições de uso;

> II - a restituição imediata da quantia paga, monetariamente atualizada, sem prejuízo de eventuais perdas e danos;

> III - o abatimento proporcional do preço."



No presente caso, a Ré foi devidamente comunicada sobre o vício em [Data da Primeira Reclamação] e, passados mais de 60 dias, não apresentou qualquer solução efetiva, extrapolando em muito o prazo legal.

* **(Aqui, buscar no `CONTEXTO ADICIONAL RECUPERADO` jurisprudência que confirme o direito do consumidor à escolha após o prazo de 30 dias. Ex: "Nesse sentido, a jurisprudência consolidada, conforme se depreende do `CONTEXTO ADICIONAL RECUPERADO` (Referência Jurisprudencial A), orienta que: '[Ementa do julgado sobre o direito de escolha do consumidor]' (TJ[Estado], Apelação Cível nº [Número], Rel. Des. [Nome], j. [Data]).")**

Desta forma, não tendo a Ré sanado o vício no prazo legal, faculta-se ao(à) Autor(a) exigir, à sua escolha, a substituição do produto por outro da mesma espécie, em perfeitas condições de uso, ou a restituição imediata da quantia paga, devidamente atualizada.

Pelo exposto, requer o(a) Autor(a) seja a Ré compelida a, alternativamente: (a) substituir o aparelho celular [Marca e Modelo] por um novo, idêntico e em perfeitas condições de uso; OU (b) restituir o valor pago de R$ [Valor Pago], devidamente corrigido monetariamente desde o desembolso e acrescido de juros legais desde a citação.



**III.3 - Do Dano Moral Configurado (*In Re Ipsa* e Teoria do Desvio Produtivo)**

A conduta da Ré extrapolou o mero dissabor ou aborrecimento cotidiano. A frustração da legítima expectativa do(a) consumidor(a) em usufruir de um bem novo e essencial, somada ao total descaso da fornecedora em solucionar o problema por um período superior a 60 (sessenta) dias, configura ato ilícito passível de reparação por dano moral.

O(A) Autor(a) foi obrigado(a) a despender tempo valioso e energia em inúmeras tentativas de contato e solução do problema (Docs. 02 e 03), caracterizando o chamado "desvio produtivo do consumidor", tese amplamente acolhida pela jurisprudência.

* **(Aqui, buscar intensamente no `CONTEXTO ADICIONAL RECUPERADO` jurisprudência sobre: (1) dano moral por vício do produto não sanado, especialmente em bens essenciais como celular; (2) dano moral pela teoria do desvio produtivo; (3) *quantum* indenizatório em casos semelhantes. Ex: "O Superior Tribunal de Justiça, em casos análogos, tem entendido que a demora excessiva e injustificada do fornecedor em solucionar vício de produto essencial configura dano moral indenizável. Vide `CONTEXTO ADICIONAL RECUPERADO` (Referência Jurisprudencial B): '[Ementa STJ]'." )**

* **(Ex: "Ademais, a teoria do Desvio Produtivo do Consumidor, que reconhece a perda de tempo útil como fato gerador de dano moral, encontra respaldo em julgados como o seguinte, extraído do `CONTEXTO ADICIONAL RECUPERADO` (Referência Jurisprudencial C): '[Ementa sobre Desvio Produtivo]' (TJ[Estado], Ap. Civ. nº [Número]).")**

O desgaste, a perda de tempo útil, a sensação de impotência e o menoscabo à sua condição de consumidor(a) vivenciados pelo(à) Autor(a) justificam a condenação da Ré ao pagamento de indenização por danos morais. Considera-se o valor de R$ 8.000,00 (oito mil reais) justo e adequado para compensar os transtornos sofridos, bem como para atender ao caráter punitivo-pedagógico da medida, evitando que a Ré reitere tal conduta desrespeitosa.

Assim, requer a condenação da Ré ao pagamento de indenização por danos morais no valor de R$ 8.000,00.



**IV - DOS PEDIDOS**

Ante o exposto, requer a Vossa Excelência:

a) A citação da Ré para, querendo, apresentar contestação no prazo legal, sob pena de revelia;

b) Seja julgada **TOTALMENTE PROCEDENTE** a presente ação para:

b.1) Condenar a Ré na obrigação de fazer consistente em [escolher e repetir: substituir o aparelho celular modelo [Marca e Modelo] por outro novo, idêntico e em perfeitas condições de uso, no prazo de X dias, sob pena de multa diária de R$ YYY,YY OU restituir ao(à) Autor(a) a quantia de R$ [Valor Pago], devidamente corrigida monetariamente desde o desembolso e acrescida de juros legais desde a citação];

b.2) Condenar a Ré ao pagamento de indenização por danos morais no valor de R$ 8.000,00 (oito mil reais), ou outro valor que Vossa Excelência entenda justo e adequado, acrescido de juros e correção monetária;

c) A condenação da Ré ao pagamento das custas processuais e honorários advocatícios, estes no importe de 20% (vinte por cento) sobre o valor da condenação (observar regras do JEC sobre honorários em 1º grau);

d) A inversão do ônus da prova, nos termos do art. 6º, VIII, do CDC;

e) (Se houver pedido de gratuidade) O deferimento do pedido de gratuidade de justiça.



**V - DAS PROVAS**Protesta provar o alegado por todos os meios de prova em direito admitidos, em especial pela juntada dos documentos que acompanham a presente, depoimento pessoal do representante da Ré, oitiva de testemunhas, e o que mais se fizer necessário.



**VI - DO VALOR DA CAUSA**

Dá-se à causa o valor de R$ [Soma do valor do produto + valor do dano moral pleiteado].



Termos em que,

Pede Deferimento.



[Local], [Data].



**[NOME DO ADVOGADO(A)]**

**OAB/[UF] nº XXX.XXX



---

Agora, com base no(s) documento(s) fornecido(s), na instrução específica do usuário e no contexto jurídico recuperado, elabore a peça processual completa, seguindo a estrutura, o tom jurídico e a formatação exemplificados."""

                        # --- FIM DO PLACEHOLDER PARA SEU SYSTEM_PROMPT ---

                        # Usando prompt_from_user_text_area que é a variável do st.text_area
                        instrucao_final_usuario_para_rag = prompt_from_user_text_area.strip() if prompt_from_user_text_area.strip() else "Elabore a peça jurídica mais adequada com base nos documentos e fatos fornecidos."

                        resposta = generate_response_with_rag(
                            system_message=system_prompt,
                            user_instruction=instrucao_final_usuario_para_rag,
                            context_document_text=st.session_state.peticao_multi_texto_extraido,
                            search_client=search_client,
                            client_openai=client_openai,
                            top_k_chunks=7 # Você pode ajustar este valor
                        )
                        resposta = str(resposta).strip()
                        st.session_state.peticao_rag_response = resposta
                        st.session_state.peticao_edited_response = resposta # Inicializa o editor com a resposta do RAG
                        st.session_state.peticao_final_version = None # Reseta a versão final
                        st.success("Peça gerada com sucesso!")
                        st.session_state.geracao_em_andamento_peticao = False # Finaliza a flag de geração
                        st.rerun() # Para garantir que o expander e a UI sejam atualizados corretamente

                    except Exception as e:
                        st.error(f"Ocorreu um erro durante a geração da peça: {e}")
                        st.session_state.peticao_rag_response = ""
                        st.session_state.peticao_edited_response = ""
                        if 'last_retrieved_chunks_details' in st.session_state:
                            del st.session_state.last_retrieved_chunks_details
                        st.session_state.geracao_em_andamento_peticao = False
                        print(f"DEBUG: Erro na geração da peça: {e}")
                        import traceback
                        traceback.print_exc()


    # --- SEÇÃO DE EXIBIÇÃO, EDIÇÃO E DOWNLOAD (CONFORME SEU CÓDIGO ORIGINAL) ---
    texto_preview = st.session_state.get('peticao_edited_response', "").strip()
    if texto_preview:
        st.markdown("---")
        st.markdown("### 3. Revisão, Edição e Exportação")

        st.markdown("#### Pré-visualização da Peça:")
        with st.container(border=True):
            st.markdown(texto_preview, unsafe_allow_html=True)

        st.markdown("---")
        texto_editado = st.text_area(
            "Edite a peça gerada (Markdown):",
            value=texto_preview, # Mantém o valor da sessão
            height=600,
            key="peticao_multi_editor" # Sua chave original
        )

        if texto_editado != st.session_state.peticao_edited_response:
            st.session_state.peticao_edited_response = texto_editado
            st.session_state.peticao_final_version = None
            st.rerun()

        # Botões de Salvar e Baixar
        col_btn1_save, col_btn2_download_space = st.columns([1,1]) # Ajuste as proporções se necessário

        with col_btn1_save:
            # Usando a chave do seu código original para o botão Salvar
            if st.button("Salvar Versão Editada", key="peticao_save_edited_btn_key"): # Chave única
                st.session_state.peticao_final_version = st.session_state.peticao_edited_response
                st.success("Versão salva.")
                # st.rerun() # Pode ser necessário para habilitar/desabilitar o botão de download imediatamente

        if st.session_state.peticao_final_version is not None:
             with col_btn2_download_space:
                try:
                    docx_data = gerar_docx(st.session_state.peticao_final_version)
                    # Usando a chave do seu código original para o botão Download
                    st.download_button(
                        label="Baixar DOCX",
                        data=docx_data,
                        file_name="LexAutomate_Peticao_Multipla.docx", # Seu nome de arquivo original
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="peticao_download_docx_final_key" # Chave única
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar DOCX: {e}")
                    print(f"DEBUG: Erro ao gerar DOCX para petição: {e}")
                    import traceback
                    traceback.print_exc()

    # --- EXPANDER PARA DETALHES DOS CHUNKS RECUPERADOS ---
    # Será exibido SE houver dados em st.session_state.last_retrieved_chunks_details
    # A função generate_response_with_rag (em rag_utils.py) é responsável por popular esta variável.
    if 'last_retrieved_chunks_details' in st.session_state and st.session_state.last_retrieved_chunks_details:
        st.markdown("---")
        with st.expander("🔎 Detalhes dos Documentos Recuperados pelo RAG (para a última geração)", expanded=False):
            for i, chunk_info in enumerate(st.session_state.last_retrieved_chunks_details):
                arquivo_origem = chunk_info.get('arquivo_origem', 'N/A')
                score = chunk_info.get('score', None)
                reranker_score = chunk_info.get('reranker_score', None)
                semantic_caption = chunk_info.get('semantic_caption', None)
                content_preview = chunk_info.get('content_preview', 'Conteúdo não disponível.')
                chunk_id = chunk_info.get('chunk_id', f"chunk_display_peticao_expander_{i}") # ID para chave

                st.markdown(f"**Chunk {i+1} (Origem: `{arquivo_origem}`)**")

                score_text = f"{score:.4f}" if isinstance(score, (int, float)) else "N/A"
                reranker_text = f"{reranker_score:.4f}" if isinstance(reranker_score, (int, float)) else "N/A"

                details_md = f"> Score Busca: **{score_text}**"
                if reranker_score is not None and reranker_text != "N/A":
                    details_md += f" | Score Reclassificação: **{reranker_text}**"
                st.markdown(details_md)

                if semantic_caption:
                    st.markdown(f"> Caption Semântico: *{semantic_caption}*")

                st.text_area(
                    label=f"Conteúdo do Chunk {i+1} (preview):",
                    value=content_preview,
                    height=100,
                    disabled=True,
                    key=f"chunk_preview_peticao_expander_key_{chunk_id}" # Chave mais robusta e única
                )
                st.markdown("---")

# Para permitir testar este arquivo isoladamente, se desejado
if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="Teste Interface de Petição - LexAutomate")
    peticao_interface()