# celestial.py
import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# Configurações / dados
# -------------------------
gula_role_name = "gula"
# thresholds para cargos baseados em mensagens (exemplo)
cargos = {
    "preguiça": 50,
    "luxúria": 500,
    "avareza": 5500,
    "inveja": 40000
}

# arquivos JSON (persistência simples)
MENSAGENS_FILE = "mensagens.json"
MOLESTAMENTO_FILE = "molestamento.json"

if os.path.exists(MENSAGENS_FILE):
    with open(MENSAGENS_FILE, "r", encoding="utf-8") as f:
        try:
            mensagens = json.load(f)
        except Exception:
            mensagens = {}
else:
    mensagens = {}

if os.path.exists(MOLESTAMENTO_FILE):
    with open(MOLESTAMENTO_FILE, "r", encoding="utf-8") as f:
        try:
            molestamento_data = json.load(f)
        except Exception:
            molestamento_data = {
                "molestados": {},
                "molestadores": {},
                "ultimo_molestamento": {}
            }
else:
    molestamento_data = {
        "molestados": {},
        "molestadores": {},
        "ultimo_molestamento": {}
    }

# -------------------------
# Utilitárias
# -------------------------
def tem_cargo_soberba_member(member: discord.Member) -> bool:
    try:
        return discord.utils.get(member.roles, name="soberba") is not None
    except Exception:
        return False

def tem_cargo_soberba_interaction(interaction: discord.Interaction) -> bool:
    user = interaction.user
    if isinstance(user, discord.Member):
        return tem_cargo_soberba_member(user)
    if interaction.guild:
        m = interaction.guild.get_member(user.id)
        return m is not None and tem_cargo_soberba_member(m)
    return False

async def aplicar_gula(member: discord.Member):
    role = discord.utils.get(member.guild.roles, name=gula_role_name)
    if role is None:
        try:
            role = await member.guild.create_role(name=gula_role_name, reason="Criando role inicial gula")
        except Exception:
            role = None
    if role and role not in member.roles:
        try:
            await member.add_roles(role)
        except Exception:
            pass

async def aplicar_cargos(member: discord.Member):
    # não aplica cargos em bots nem em quem tem 'soberba'
    if member.bot or tem_cargo_soberba_member(member):
        return
    user_count = mensagens.get(str(member.id), 0)
    for nome, quantidade in cargos.items():
        role = discord.utils.get(member.guild.roles, name=nome)
        if role is None:
            try:
                role = await member.guild.create_role(name=nome, reason="Criando role de milestone")
            except Exception:
                role = None
        if role and user_count >= quantidade and role not in member.roles:
            try:
                await member.add_roles(role)
            except Exception:
                pass
            # notifica no canal "confessionário" ou primeiro canal de texto
            canal = discord.utils.get(member.guild.text_channels, name="confessionário")
            if not canal and member.guild.text_channels:
                canal = member.guild.text_channels[0]
            if canal:
                embed = discord.Embed(
                    title="🎉 novo cargo conquistado!",
                    description=f"{member.mention} subiu para o cargo **{nome}**!",
                    color=discord.Color.green()
                )
                try:
                    await canal.send(embed=embed)
                except Exception:
                    pass

def member_name_from_id(guild: discord.Guild, user_id: str):
    try:
        user = guild.get_member(int(user_id))
        return user.name if user else "desconhecido"
    except Exception:
        return "desconhecido"

def salvar_mensagens():
    try:
        with open(MENSAGENS_FILE, "w", encoding="utf-8") as f:
            json.dump(mensagens, f)
    except Exception:
        pass

def salvar_molestamento():
    try:
        with open(MOLESTAMENTO_FILE, "w", encoding="utf-8") as f:
            json.dump(molestamento_data, f)
    except Exception:
        pass

# -------------------------
# Eventos
# -------------------------
@bot.event
async def on_ready():
    print(f"✅ {bot.user} está online (Celestial).")
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} comandos sincronizados.")
    except Exception as e:
        print("Erro ao sincronizar comandos:", e)
    # aplica gula / cargos para membros já presentes
    for guild in bot.guilds:
        for member in guild.members:
            try:
                await aplicar_gula(member)
                await aplicar_cargos(member)
            except Exception:
                pass

@bot.event
async def on_member_join(member: discord.Member):
    try:
        await aplicar_gula(member)
    except Exception:
        pass

@bot.event
async def on_message(message: discord.Message):
    # ignora bots
    if message.author.bot:
        return

    # contagem de mensagens
    user_id = str(message.author.id)
    mensagens[user_id] = mensagens.get(user_id, 0) + 1
    try:
        await aplicar_cargos(message.author)
    except Exception:
        pass
    salvar_mensagens()

    # processa outros comandos (slash)
    await bot.process_commands(message)

# -------------------------
# Slash commands (Celestial)
# -------------------------

# /menu
@bot.tree.command(name="menu", description="Mostra o menu principal do bot Celestial.")
async def menu(interaction: discord.Interaction):
    texto = "📜 **comandos disponíveis:**\n\n"
    texto += "💬 **gerais:**\n/menu → mostra este menu\n/contador [usuário] → mostra quantas mensagens enviou\n/rank → top 10 mensagens\n\n"
    texto += ":performing_arts: **comandos de molestamento:**\n/molestar alvo → molestar alguém\n/molestados → top 10 mais molestados\n/molestador → top 10 que mais molestam\n/molestei → quantas pessoas você molestou\n/molestaram → quantas pessoas te molestaram\n\n"
    texto += "⚙️ **admin (soberba):**\n/resetar → reseta rank/cargos (somente soberba)"
    embed = discord.Embed(title="🎭 Menu - Celestial", description=texto, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

# /contador
@bot.tree.command(name="contador", description="Mostra quantas mensagens um usuário enviou (ou você se omitido).")
@app_commands.describe(usuario="Usuário para checar (opcional)")
async def contador(interaction: discord.Interaction, usuario: discord.Member = None):
    if usuario is None:
        usuario = interaction.user
    count = mensagens.get(str(usuario.id), 0)
    embed = discord.Embed(
        title="📊 contador de mensagens",
        description=f"{usuario.mention} enviou **{count}** mensagens.",
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed)

# /rank
@bot.tree.command(name="rank", description="Top 10 mensagens.")
async def rank(interaction: discord.Interaction):
    ranking = sorted(mensagens.items(), key=lambda x: x[1], reverse=True)[:10]
    embed = discord.Embed(title="🏆 Top 10 — mensagens", color=discord.Color.gold())
    if not ranking:
        embed.description = "nenhuma mensagem registrada ainda."
    else:
        texto = ""
        for i, (user_id, count) in enumerate(ranking, start=1):
            nome = member_name_from_id(interaction.guild, user_id) if interaction.guild else "desconhecido"
            texto += f"{i}. {nome} — {count} mensagens\n"
        embed.description = texto
    await interaction.response.send_message(embed=embed)

# /resetar (soberba)
@bot.tree.command(name="resetar", description="Reseta rank/cargos (somente soberba).")
async def resetar(interaction: discord.Interaction):
    if not tem_cargo_soberba_interaction(interaction):
        await interaction.response.send_message("🚫 você não tem permissão (soberba).", ephemeral=True)
        return

    mensagens.clear()
    salvar_mensagens()

    for guild in bot.guilds:
        for member in guild.members:
            if member.bot or tem_cargo_soberba_member(member):
                continue
            try:
                # remove cargos de milestone (não remove @everyone)
                cargos_para_remover = [r for r in member.roles if r.name in cargos.keys()]
                if cargos_para_remover:
                    await member.remove_roles(*cargos_para_remover)
                await aplicar_gula(member)
            except Exception:
                pass

    # reaplica cargos conforme contagem (agora zero, então só gula)
    for guild in bot.guilds:
        for member in guild.members:
            try:
                await aplicar_cargos(member)
            except Exception:
                pass

    embed = discord.Embed(
        title="♻️ Rank resetado",
        description="Todos voltaram para **gula** e mensagens foram zeradas.",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)

# -------------------------
# Molestamento commands
# -------------------------

# /molestar
@bot.tree.command(name="molestar", description="Molesta um alvo (brincadeira).")
@app_commands.describe(alvo="Usuário alvo")
async def molestar(interaction: discord.Interaction, alvo: discord.Member):
    if alvo.bot:
        await interaction.response.send_message("❌ não pode molestar bot.", ephemeral=True)
        return
    if alvo == interaction.user:
        await interaction.response.send_message("tem que ser muito doente pra querer se comer", ephemeral=True)
        return
    if tem_cargo_soberba_interaction(interaction) is False and tem_cargo_soberba_member(alvo):
        await interaction.response.send_message("você não pode molestar seu papai.", ephemeral=True)
        return

    autor_id = str(interaction.user.id)
    alvo_id = str(alvo.id)
    if not tem_cargo_soberba_interaction(interaction):
        chave_cooldown = f"{autor_id}_{alvo_id}"
        ultimo = molestamento_data["ultimo_molestamento"].get(chave_cooldown)
        if ultimo:
            tempo_passado = datetime.utcnow().timestamp() - ultimo
            if tempo_passado < 900:  # 15 minutos
                tempo_restante = 900 - tempo_passado
                minutos = int(tempo_restante // 60)
                segundos = int(tempo_restante % 60)
                await interaction.response.send_message(f"⏰ calma aí! espere **{minutos}min {segundos}s** para molestar {alvo.mention} novamente.", ephemeral=True)
                return

    molestamento_data["molestados"][alvo_id] = molestamento_data["molestados"].get(alvo_id, 0) + 1
    molestamento_data["molestadores"][autor_id] = molestamento_data["molestadores"].get(autor_id, 0) + 1
    if not tem_cargo_soberba_interaction(interaction):
        molestamento_data["ultimo_molestamento"][f"{autor_id}_{alvo_id}"] = datetime.utcnow().timestamp()
    salvar_molestamento()

    embed = discord.Embed(
        title=":performing_arts: molestamento realizado!",
        description=f"{interaction.user.mention} molestou {alvo.mention}! 🤪",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)

# /molestados
@bot.tree.command(name="molestados", description="Top 10 mais molestados.")
async def molestados(interaction: discord.Interaction):
    ranking = sorted(molestamento_data["molestados"].items(), key=lambda x: x[1], reverse=True)[:10]
    embed = discord.Embed(title=":performing_arts: Top 10 — mais molestados", color=discord.Color.red())
    if not ranking:
        embed.description = "ninguém foi molestado ainda... 😢"
    else:
        texto = ""
        for i, (user_id, count) in enumerate(ranking, start=1):
            nome = member_name_from_id(interaction.guild, user_id) if interaction.guild else "desconhecido"
            texto += f"{i}. {nome} — {count} vezes\n"
        embed.description = texto
    await interaction.response.send_message(embed=embed)

# /molestador
@bot.tree.command(name="molestador", description="Top 10 que mais molestam.")
async def molestador(interaction: discord.Interaction):
    ranking = sorted(molestamento_data["molestadores"].items(), key=lambda x: x[1], reverse=True)[:10]
    embed = discord.Embed(title=":performing_arts: Top 10 — que mais molestam", color=discord.Color.orange())
    if not ranking:
        embed.description = "ninguém molestou ainda... 😴"
    else:
        texto = ""
        for i, (user_id, count) in enumerate(ranking, start=1):
            nome = member_name_from_id(interaction.guild, user_id) if interaction.guild else "desconhecido"
            texto += f"{i}. {nome} — {count} pessoas\n"
        embed.description = texto
    await interaction.response.send_message(embed=embed)

# /molestei
@bot.tree.command(name="molestei", description="Quantas pessoas você já molestou.")
async def molestei(interaction: discord.Interaction):
    autor_id = str(interaction.user.id)
    count = molestamento_data["molestadores"].get(autor_id, 0)
    embed = discord.Embed(
        title=":performing_arts: seu total de molestamentos",
        description=f"você já molestou **{count}** pessoas! 😈",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)

# /molestaram
@bot.tree.command(name="molestaram", description="Quantas vezes você foi molestado.")
async def molestaram(interaction: discord.Interaction):
    autor_id = str(interaction.user.id)
    count = molestamento_data["molestados"].get(autor_id, 0)
    embed = discord.Embed(
        title=":performing_arts: vezes que foi molestado",
        description=f"você já foi molestado **{count}** vezes! 😭",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    token = os.getenv("TOKEN")
    if not token:
        print("❌ ERRO: variável TOKEN não encontrada. Defina TOKEN no ambiente.")
    else:
        bot.run(token)
