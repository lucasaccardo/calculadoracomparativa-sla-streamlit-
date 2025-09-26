# st.session_state.pecas_temp[numero] é a sua lista de peças.
# Ex: [{"nome": "Filtro de Óleo", "valor": 50.0}, {"nome": "Vela de Ignição", "valor": 80.0}]

if st.session_state.pecas_temp[numero]:
    st.write("### 🛠️ Gerenciar Peças Adicionadas:")

    # Cria um DataFrame com as peças para facilitar a visualização
    df_pecas = pd.DataFrame(st.session_state.pecas_temp[numero])
    df_pecas_display = df_pecas.copy() # Cria uma cópia para exibição
    df_pecas_display["Valor"] = df_pecas_display["valor"].apply(formatar_moeda)
    df_pecas_display.rename(columns={"nome": "Peça"}, inplace=True)
    
    st.table(df_pecas_display[["Peça", "Valor"]]) # Mostra a tabela apenas uma vez

    st.markdown("---") # Divisor visual

    # --- A MÁGICA ACONTECE AQUI ---
    # Cria uma lista de opções para o multiselect a partir dos nomes das peças
    opcoes_pecas = df_pecas['nome'].tolist()

    # O widget multiselect permite selecionar várias peças para remover
    pecas_para_remover = st.multiselect(
        "Selecione as peças que deseja remover:",
        options=opcoes_pecas,
        key=f"multiselect_remover_pecas_{numero}"
    )

    # Botão único para confirmar a remoção
    if st.button(f"🗑️ Remover Peças Selecionadas", key=f"botao_remover_{numero}"):
        if not pecas_para_remover:
            st.warning("⚠️ Nenhuma peça foi selecionada para remoção.")
        else:
            # Filtra a lista original, mantendo apenas as peças que NÃO foram selecionadas para remoção
            st.session_state.pecas_temp[numero] = [
                peca for peca in st.session_state.pecas_temp[numero] 
                if peca['nome'] not in pecas_para_remover
            ]
            st.success("✅ Peças removidas com sucesso!")
            st.rerun() # Força a recarga da página para atualizar a tabela e o multiselect
else:
    st.info("Nenhuma peça adicionada a este cenário ainda.")
