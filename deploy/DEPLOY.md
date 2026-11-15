# Deploy do Arara numa VPS (modo evento)

O que sobe: **Postgres** (só na rede interna), **backend** (Spring Boot, que também serve o globo, `estudo/`,
`furnas/` e `uruguai/`) e **Caddy** na frente (porta 80; 443 com HTTPS automático quando houver domínio).
As análises já feitas vêm dos seeds. Nada de NISAR é processado na VPS: o monitor fica desligado, por
isso não há credenciais Earthdata nem pipeline Python na imagem.

## Requisitos

- Ubuntu 22.04 ou 24.04, 2 vCPU, 4 GB de RAM, 20 GB de disco.
- Docker Engine com o plugin compose (`docker compose version` funciona).
- Portas 80 e 443 livres e liberadas no provedor.
- Os dois seeds, gerados na máquina de desenvolvimento com `python deploy/gerar_seeds.py`:
  `deploy/seed/arara_seed.sql.gz` e `deploy/seed/arara_data.tar.gz` (não estão no Git).

Instalar o Docker no Ubuntu, se ainda não tiver:

```
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER    # saia e entre de novo na sessão
```

## 1. Firewall

```
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
```

## 2. Código e seeds

Na VPS:

```
git clone -b arara-app https://github.com/gabriel-moraes03/arara.git
mkdir -p arara/deploy/seed
```

Da sua máquina (na raiz do repositório), copie os seeds:

```
scp deploy/seed/arara_seed.sql.gz deploy/seed/arara_data.tar.gz usuario@IP_DA_VPS:arara/deploy/seed/
```

## 3. Configuração

```
cd arara/deploy
cp .env.example .env
nano .env        # ARARA_DB_PASSWORD obrigatório; DOMAIN opcional (ver seção 6)
chmod 600 .env
```

Gere uma senha com `openssl rand -base64 24`. Não ponha credenciais Earthdata: o modo evento não usa.

## 4. Subir e carregar as análises

```
chmod +x restore.sh
./restore.sh
```

O script constrói a imagem do backend, sobe banco e backend, extrai os arquivos no volume, importa o banco
(só se estiver vazio), reinicia o backend e sobe o Caddy. Pode rodar de novo sem duplicar nada.
A primeira vez leva alguns minutos (build com Maven).

## 5. Conferir

```
docker compose -f docker-compose.prod.yml ps            # os três "running", backend "healthy"
curl -s http://localhost/api/arara/config               # "algorithm_version": "arara-water-0.3.0"
curl -s http://localhost/api/arara/monitor              # "enabled": false
curl -s "http://localhost/api/arara/analyses?status=completed" | head -c 300
```

No navegador: `http://IP_DA_VPS/` (globo com as regiões), `/furnas/` e `/uruguai/` (também pelo rodapé).

Logs:

```
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f caddy
```

## 6. HTTPS com domínio

1. Crie um registro DNS `A` do domínio (ex.: `arara.exemplo.org`) para o IP da VPS e espere propagar.
2. Em `deploy/.env`: `DOMAIN=arara.exemplo.org`.
3. `docker compose -f docker-compose.prod.yml up -d caddy`

O Caddy pede o certificado Let's Encrypt sozinho e redireciona HTTP para HTTPS. Sem domínio
(`DOMAIN` vazio), o site fica em HTTP puro na porta 80, pelo IP.

## 7. Atualizar e reiniciar

```
cd arara && git pull
cd deploy && docker compose -f docker-compose.prod.yml up -d --build
```

Os volumes (`arara-pg`, `arara-data`, certificados do Caddy) continuam. Só reiniciar:

```
docker compose -f docker-compose.prod.yml restart
```

Parar sem perder dados: `docker compose -f docker-compose.prod.yml down` (nunca `down -v`, que apaga os volumes).

## Atrás de um Traefik já existente

Quando a VPS já tem um Traefik ocupando as portas 80 e 443, o Caddy do Arara fica atrás dele, sem
publicar essas portas nem pedir certificado: quem termina o HTTPS é o Traefik.

1. Em `deploy/.env`, tire o Caddy das portas do Traefik e deixe o domínio vazio (o Caddy serve HTTP
   puro na 80 interna):

   ```
   HTTP_PORT=8088
   HTTPS_PORT=8443
   DOMAIN=
   ```

2. Copie o exemplo (o arquivo copiado fica fora do Git) e troque `arara.example.org` pelo seu domínio:

   ```
   cp docker-compose.traefik.example.yml docker-compose.traefik.yml
   nano docker-compose.traefik.yml
   ```

   A porta da label `loadbalancer.server.port` é a **80 interna** do container, não a `HTTP_PORT`: o
   Traefik fala direto com o IP do container, na rede Docker. Por isso o Traefik precisa alcançar a
   rede do compose do Arara (`arara-prod_default`).

3. Todo comando passa a usar os dois arquivos:

   ```
   docker compose -f docker-compose.prod.yml -f docker-compose.traefik.yml up -d --build
   docker compose -f docker-compose.prod.yml -f docker-compose.traefik.yml ps
   ```

   O `restore.sh` só usa o `docker-compose.prod.yml`; depois dele, recrie o Caddy com as labels:
   `docker compose -f docker-compose.prod.yml -f docker-compose.traefik.yml up -d caddy`.

Erros comuns:

- Crases ou aspas perdidas na regra `Host`: tem de ser `Host("arara.exemplo.org")` (ou com crases,
  `` Host(`arara.exemplo.org`) ``), com o domínio inteiro entre os delimitadores.
- `ParseBool` em `traefik.enable`: no formato de lista (`- "traefik.enable=true"`), aspas duplas em
  volta do `true` (`- traefik.enable="true"`) chegam ao Traefik como texto com aspas e ele recusa. Use o
  formato de mapa do exemplo ou a lista sem aspas internas.

## Modo evento: o que está ligado e desligado

| Variável (deploy/.env) | Padrão | Efeito |
|---|---|---|
| `ARARA_MONITOR` | `false` | monitor das regiões desligado: nenhum job, nenhuma leitura na NASA |
| `ARARA_RETENTION_DAYS` | `36500` | a limpeza agendada não apaga análises durante a avaliação |
| `DOMAIN` | vazio | vazio = HTTP na 80; com domínio = HTTPS automático |
| `ARARA_DB_USER`, `ARARA_DB_PASSWORD` | `arara`, (obrigatória) | banco, só na rede interna do compose |

- A API só tem rotas `GET`; `POST`, `PUT` e `DELETE` respondem 405.
- Erros da API saem em JSON curto (`status`, `reason`), sem stack trace.
- O backend não envia cabeçalhos CORS: o navegador só aceita chamadas do próprio domínio.
- Só o Caddy publica portas; banco e backend não são acessíveis de fora.
