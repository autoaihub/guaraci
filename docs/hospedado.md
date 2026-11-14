# Guaraci hospedado

Com `GUARACI_MODE=hosted`, o Guaraci deixa de ser uma ferramenta que cada pessoa instala e passa a rodar num servidor compartilhado, com a mesma interface web. Quem usa só precisa de navegador e de uma conta aprovada. Sem a variável, nada muda: a API continua local, sem login e sem registro de uso.

O código do modo fica em `guaraci/hosted/`; a fila multiusuário, em `guaraci/services/jobs.py` com a política de `guaraci/services/job_policy.py`; e o material de implantação, em `deploy/hospedado/`.

## Como funciona

A pessoa pede acesso pela própria interface (nome, e-mail, instituição, finalidade e aceite da política de privacidade) e a conta fica pendente até um administrador aprovar. Depois do login, ela navega pelo catálogo e pede coletas como na versão local. A diferença é que a coleta entra numa fila no servidor e, quando termina, os arquivos aparecem para download por links assinados, válidos por 6 horas. Os arquivos ficam no servidor por 48 horas e então são apagados.

A fila roda dentro do processo da API, por isso o serviço sobe com **um único processo** do uvicorn. As vagas são divididas em rodízio: com duas vagas e um usuário com três coletas na fila, quem chega depois não espera as três terminarem.

### Proteções

| Risco | Proteção | Onde |
|---|---|---|
| Senha vazada do banco | Hash Argon2; só o hash é guardado | `hosted/accounts.py` |
| Força bruta no login | Bloqueio após 5 falhas por e-mail ou 20 por IP em 15 min, com espera crescente de 60 s até 1 h; mensagem igual para e-mail inexistente e senha errada | `hosted/accounts.py` |
| Roubo de sessão | Cookie `__Host-` HttpOnly, Secure e SameSite=Lax; no banco fica só o SHA-256 do token; sessão vence após 12 h sem uso | `hosted/accounts.py`, `hosted/runtime.py` |
| Requisição forjada (CSRF) | Token por sessão no cabeçalho `X-CSRF-Token` e conferência do `Origin` | `hosted/runtime.py` |
| Excesso de requisições | Balde de fichas por IP (120/min), login (10/min), cadastro (5/h), estimativa (30/h) e coleta (30/h); corpo de POST limitado a 64 KB | `hosted/ratelimit.py`, `hosted/runtime.py` |
| Servidor sobrecarregado | 2 coletas simultâneas no total, 1 por usuário, 3 ativas por usuário, 10 por dia, 40 na fila inteira; recusa nova coleta com menos de 5 GB livres | `services/job_policy.py` |
| Coleta gigante | Estimativa de volume antes de enfileirar (recusa acima de 2 GB) e corte em execução por volume e por tempo (120 min) | `services/jobs.py` |
| Acesso a arquivo alheio | Pasta de saída imposta pelo servidor por usuário e por coleta; job de outro usuário responde 404; link de download assinado com HMAC e sem travessia de pasta | `services/jobs.py`, `hosted/artifacts.py` |
| Vazamento de caminho do servidor | Respostas da API saem sem o caminho da raiz de saídas | `hosted/runtime.py` |
| Rotas que só fazem sentido local | `/docs`, `/openapi.json`, `/downloads/*` e "abrir pasta" respondem 404 | `hosted/runtime.py` |
| Página embutida em outro site, XSS | CSP com `script-src 'self'`, `frame-ancestors 'none'`, `X-Content-Type-Options`, HSTS | `hosted/runtime.py` |

Todos os números acima são o padrão de `hosted/settings.py` e mudam pelo arquivo de ambiente (`deploy/hospedado/guaraci.env.example`).

### Registro de uso

Ficam registrados cadastro, login (com falhas e bloqueios), saída, telas visitadas, estimativas, coletas pedidas, recusadas, canceladas e refeitas, downloads e ações de administração, cada um com data, usuário, sessão, IP e navegador. O painel de administração mostra usuários ativos, IPs distintos, logins, coletas e downloads por dia, as fontes mais pedidas, as telas mais vistas e a jornada de cada usuário.

Como IP é dado pessoal, o registro segue a política de `/privacidade`: depois de 30 dias o IP é reduzido à rede (/24 no IPv4, /48 no IPv6) e o navegador vira só a família; depois de 365 dias o evento é apagado. A exclusão de uma conta desliga dela os eventos que restarem. A faxina roda a cada 15 minutos dentro do próprio serviço.

## Implantação no VLXGUARACI

A máquina é um Debian 13 com Python 3.13, sem Docker e sem sudo para a conta `sabia`. O serviço escuta HTTP na porta 8080 e o TLS termina no proxy reverso da UTFPR, que publica `guaraci.sabiadatalake.com.br`.

```bash
git clone https://github.com/autoaihub/guaraci.git ~/guaraci
cd ~/guaraci && git checkout feat/guaraci-hospedado   # enquanto não estiver na main
bash deploy/hospedado/instalar.sh
nano ~/guaraci.env          # GUARACI_PROXY_IP e GUARACI_CONTACT
set -a; . ~/guaraci.env; set +a
.venv/bin/guaraci admin create --email <e-mail do administrador>
bash deploy/hospedado/instalar.sh --servico
```

O `instalar.sh` cria o ambiente (com `python3 -m venv` ou, se o Debian não tiver o `python3-venv`, com o `uv` instalado na conta), instala os extras `datasus`, `api` e `trabalho`, gera `~/guaraci.env` com segredo novo e permissão 600 e confere se a API carrega no modo hospedado. Com `--servico`, registra a unidade de usuário do systemd.

A unidade de usuário só continua no ar sem sessão aberta se o administrador da máquina rodar uma vez `sudo loginctl enable-linger sabia`. Sem isso, a alternativa é o crontab da conta:

```
@reboot $HOME/guaraci/deploy/hospedado/iniciar.sh >> $HOME/guaraci-dados/guaraci.log 2>&1
```

Para atualizar: `git pull` e `bash deploy/hospedado/instalar.sh`, seguido de `systemctl --user restart guaraci`. Coletas em andamento no momento do reinício voltam como falha e podem ser refeitas pela interface.

### O que o proxy precisa fazer

- Encaminhar `https://guaraci.sabiadatalake.com.br` para `http://10.10.20.12:8080`, a única porta exposta. A 9000 é o SSH e não deve ir para fora.
- Mandar `X-Forwarded-For` e `X-Forwarded-Proto: https`. O IP do proxy vai em `GUARACI_PROXY_IP`; só dele o Guaraci aceita esses cabeçalhos.
- Não armazenar em cache as respostas (a API depende de sessão) e permitir respostas longas em fluxo, porque o ZIP com todos os arquivos é gerado durante o download. Um tempo de leitura de 10 minutos basta.
- Se possível, liberar a porta 8080 só para o IP do proxy na rede interna.

### O que depende da infraestrutura

- **FTP de saída.** As bases do DATASUS (SIM, SINAN, SIH, SIA, CNES e outras) vêm de `ftp.datasus.gov.br`, e a saída na porta 21 está bloqueada no servidor. Enquanto não for liberada (porta 21 e as portas passivas), essas fontes falham; as que usam HTTPS funcionam.
- **Memória e disco.** Com 4 GB de RAM e 46 GB de disco, o padrão de 2 coletas simultâneas e 2 GB por coleta é o teto prudente. Para coletas maiores, a máquina precisaria de pelo menos 8 GB de RAM e de um volume separado para `GUARACI_OUTPUT_ROOT`.

## Administração

Pela interface, o administrador vê o painel, aprova ou recusa pedidos, bloqueia contas, ajusta a cota diária de cada usuário e cancela coletas. Pela linha de comando, com o ambiente carregado:

| Comando | Faz |
|---|---|
| `guaraci admin create --email E` | Cria administrador já aprovado (pede a senha) |
| `guaraci admin list [--status pending]` | Lista as contas |
| `guaraci admin approve E` / `disable E` | Aprova ou bloqueia (bloquear encerra as sessões) |
| `guaraci admin promote E` | Torna administrador |
| `guaraci admin set-password E` | Troca a senha e encerra as sessões |
| `guaraci admin backup ARQUIVO` | Copia o banco com o serviço no ar |

O banco (`GUARACI_DB_PATH`) guarda contas, sessões e registros; o estado da fila fica ao lado dele, em `download_jobs.json`. São esses dois arquivos que entram no backup; as saídas das coletas são descartáveis.
