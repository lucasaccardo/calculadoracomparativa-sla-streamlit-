# Guia de Implantação no Azure App Service

Este guia detalha o passo a passo para implantar o aplicativo Streamlit **Frotas Vamos SLA** no Azure App Service com Linux e Python 3.11.

## Pré-requisitos

- Assinatura ativa do Azure
- Conta GitHub com acesso ao repositório
- Azure CLI instalado (opcional, mas recomendado)

## Passo 1: Criar o Web App no Azure

1. Acesse o [Portal do Azure](https://portal.azure.com)
2. Clique em **"Criar um recurso"** > **"Web App"**
3. Configure os seguintes parâmetros:
   - **Grupo de Recursos**: Crie um novo ou selecione um existente (ex: `rg-frotas-sla`)
   - **Nome**: Escolha um nome único para seu app (ex: `frotas-vamos-sla`)
     - Seu app ficará disponível em: `https://frotas-vamos-sla.azurewebsites.net`
   - **Publicar**: Código
   - **Pilha de runtime**: Python 3.11
   - **Sistema Operacional**: Linux
   - **Região**: Escolha a região mais próxima (ex: Brazil South, East US)
   - **Plano do Linux**: Crie um novo ou use existente (recomendado: B1 ou superior)
4. Clique em **"Revisar + criar"** e depois em **"Criar"**

## Passo 2: Configurar Variáveis de Ambiente (App Settings)

Após a criação do Web App, adicione as seguintes configurações de aplicativo:

1. No portal do Azure, navegue até seu Web App
2. No menu lateral, selecione **"Configuração"** > **"Configurações do aplicativo"**
3. Adicione as seguintes variáveis (clique em **"Nova configuração de aplicativo"** para cada uma):

### Configurações Obrigatórias

| Nome | Valor | Descrição |
|------|-------|-----------|
| `WEBSITES_PORT` | `8000` | Porta em que o Streamlit será executado |
| `APP_BASE_URL` | `https://SEUAPP.azurewebsites.net` | URL base do seu aplicativo (substitua SEUAPP) |
| `USERS_PATH` | `/home/data/users.csv` | Caminho persistente para o arquivo de usuários |
| `SUPERADMIN_DEFAULT_PASSWORD` | `SuaSenhaSegura123!` | Senha inicial do superadmin (mínimo 10 caracteres, com maiúscula, minúscula, número e especial) |

### Configurações Opcionais (E-mail/SMTP)

Se desejar habilitar envio de e-mails (redefinição de senha, aprovação de conta):

| Nome | Valor | Descrição |
|------|-------|-----------|
| `EMAIL_HOST` | `smtp.office365.com` | Servidor SMTP (exemplo Office 365) |
| `EMAIL_PORT` | `587` | Porta SMTP |
| `EMAIL_USERNAME` | `seu-email@exemplo.com` | Usuário de autenticação SMTP |
| `EMAIL_PASSWORD` | `sua-senha-email` | Senha do e-mail |
| `EMAIL_USE_TLS` | `True` | Usar TLS para conexão segura |
| `EMAIL_FROM` | `noreply@exemplo.com` | Endereço de remetente dos e-mails |

4. Clique em **"Salvar"** no topo da página

## Passo 3: Configurar o Comando de Inicialização

1. Ainda na página **"Configuração"** do seu Web App
2. Na aba **"Configurações gerais"**
3. No campo **"Comando de inicialização"**, insira:

```bash
python -m streamlit run streamlit_app.py --server.port 8000 --server.address 0.0.0.0 --browser.gatherUsageStats false
```

4. Clique em **"Salvar"**

## Passo 4: Conectar ao GitHub (Deployment Center)

1. No menu lateral do seu Web App, selecione **"Centro de Implantação"**
2. Selecione **"GitHub"** como fonte
3. Clique em **"Autorizar"** e faça login na sua conta GitHub
4. Configure:
   - **Organização**: Selecione sua organização ou conta
   - **Repositório**: Selecione o repositório `frotavamossla`
   - **Branch**: `main`
5. Clique em **"Salvar"**

O Azure criará automaticamente um workflow do GitHub Actions no seu repositório (`.github/workflows/`).

## Passo 5: Habilitar Application Insights (Logs e Monitoramento)

1. No menu lateral do seu Web App, selecione **"Application Insights"**
2. Clique em **"Ativar Application Insights"**
3. Selecione **"Criar novo recurso"** ou use um existente
4. Clique em **"Aplicar"**

Para visualizar logs:
- Vá em **"Monitoramento"** > **"Stream de log"** para ver logs em tempo real
- Ou use **"Application Insights"** > **"Logs"** para consultas avançadas

## Passo 6: Primeiro Acesso

Após a implantação bem-sucedida:

1. Acesse `https://SEUAPP.azurewebsites.net` (substitua SEUAPP pelo nome do seu app)
2. Faça login com as credenciais do superadmin:
   - **Usuário**: `lucas.sureira` (fixo no código)
   - **Senha**: A senha que você definiu em `SUPERADMIN_DEFAULT_PASSWORD`
3. No primeiro acesso, você será solicitado a aceitar os termos de uso
4. Caso a senha tenha expirado, será solicitado alterá-la

## Passo 7: Gerenciar Usuários

Como superadmin, você pode:
- Aprovar cadastros pendentes
- Adicionar novos usuários
- Conceder permissões de administrador
- Enviar links de redefinição de senha

## Notas Importantes sobre Persistência

### Armazenamento em `/home`

- O diretório `/home` no Azure App Service (Linux) é **persistente** entre reinicializações
- Ideal para desenvolvimento e ambientes de instância única
- O arquivo `users.csv` será armazenado em `/home/data/users.csv`

### Limitações

⚠️ **IMPORTANTE**: Para ambientes de produção com múltiplas instâncias ou alta disponibilidade:

- O armazenamento local `/home` **não é compartilhado** entre múltiplas instâncias
- Recomendações para produção:
  - **Azure Files**: Monte um compartilhamento de arquivos Azure Files em `/home/data`
  - **Azure Blob Storage**: Migre o armazenamento de usuários para Blob Storage
  - **Azure SQL Database**: Migre para um banco de dados relacional (melhor opção para produção)

### Backups

- Habilite backups automáticos do Web App no Azure (configuração disponível no portal)
- Considere exportar periodicamente o arquivo `users.csv` para um armazenamento externo

## Solução de Problemas

### O aplicativo não inicia

1. Verifique os logs em **"Stream de log"** ou **"Application Insights"**
2. Confirme que todas as variáveis de ambiente estão configuradas corretamente
3. Verifique se o comando de inicialização está correto
4. Certifique-se de que o `requirements.txt` está na raiz do repositório

### Erro de autenticação

1. Verifique se `SUPERADMIN_DEFAULT_PASSWORD` está definido corretamente
2. A senha deve atender aos requisitos: mínimo 10 caracteres, com maiúscula, minúscula, número e caractere especial
3. Se necessário, redefina a senha via linha de comando ou recrie o arquivo de usuários

### E-mails não estão sendo enviados

1. Verifique as configurações SMTP em **"Configuração"** > **"Configurações do aplicativo"**
2. Teste a conexão SMTP usando a ferramenta de teste de e-mail no painel de administração
3. Verifique os logs para mensagens de erro relacionadas a SMTP

### Problemas de desempenho

1. Considere aumentar o plano do App Service (ex: de B1 para B2 ou superior)
2. Habilite o cache do Streamlit (já implementado no código)
3. Monitore o uso de recursos em **"Métricas"**

## Manutenção

### Atualizar o Aplicativo

Qualquer push para a branch `main` no GitHub acionará automaticamente uma nova implantação via GitHub Actions.

### Escalabilidade

Para escalar horizontalmente (múltiplas instâncias):

1. Vá em **"Escalar horizontalmente (App Service plan)"**
2. Configure o número de instâncias
3. ⚠️ **Lembre-se**: Você precisará migrar o armazenamento de `users.csv` para uma solução compartilhada (Azure Files, Blob Storage ou SQL Database)

### Monitoramento Contínuo

- Configure alertas no Application Insights para falhas ou lentidão
- Revise periodicamente os logs de acesso e erros
- Monitore o uso de recursos (CPU, memória, armazenamento)

## Recursos Adicionais

- [Documentação do Azure App Service](https://docs.microsoft.com/azure/app-service/)
- [Documentação do Streamlit](https://docs.streamlit.io/)
- [Azure Application Insights](https://docs.microsoft.com/azure/azure-monitor/app/app-insights-overview)

## Suporte

Para problemas relacionados ao aplicativo, entre em contato com o time de desenvolvimento ou o administrador do sistema.
