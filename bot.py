import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta
import asyncio

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------------
# Configurações / dados
# -------------------------
gula_role_name = "gula"
cargos = {
    "preguiça": 50,
    "luxúria": 500,
    "avareza": 5500,
    "inveja": 40000
}

bots_permitidos = [1430020048579334236, 411916947773587456]
disboard_id = 302050872383242240
antilink_ativo = True
auto_handle_new_bots = True
auto_delete_bot_messages = True

# arquivos JSON
if os.path.exists("mensagens.json"):
    with open("mensagens.json", "r") as f:
        mensagens = json.load(f)
else:
    mensagens = {}

if os.path.exists("mutes.json"):
    with open("mutes.json", "r") as f:
        mutes = json.load(f)
else:
    mutes = {}

if os.path.exists("molestamento.json"):
    with open("molestamento.json", "r") as f:
        molestamento_data = json.load(f)
else:
    molestamento_data = {
        "molestados": {},
        "molestadores": {},
        "ultimo_molestamento": {}
    }

# -------------------------
# Utilitárias
# -------------------------
async def aplicar_gula(member: discord.Member):
    role = discord.utils.get(member.guild.roles, name=gula_role_name)
    if role is None:
        try:
            role = await member.guild.create_role(name=gula_role_name)
        except Exception:
            role = None
    if role and role not in member.roles:
        try:
            await member.add_roles(role)
        except Exception:
            pass

async def aplicar_cargos(member: discord.Member):
    if member.bot or discord.utils.get(member.roles, name="soberba"):
        return
    for nome, quantidade in cargos.items():
        role = discord.utils.get(member.guild.roles, name=nome)
        if role is None:
            try:
                role = await member.guild.create_role(name=nome)
            except Exception:
                role = None
        if role and mensagens.get(str(member.id), 0) >= quantidade and role not in member.roles:
            try:
                await member.add_roles(role)
            except Exception:
                pass
            canal = discord.utils.get(member.guild.text_channels, name="geral")
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

async def ensure_muted_role(guild: discord.Guild):
    role = discord.utils.get(guild.roles, name="mutado")
    if role is None:
        try:
            role = await guild.create_role(name="mutado")
        except Exception:
            role = None
    if role:
        for canal in guild.channels:
            try:
                await canal.set_permissions(role, send_messages=False, speak=False)
            except Exception:
                pass
    return role

def tem_cargo_soberba_member(member: discord.Member) -> bool:
    try:
        return discord.utils.get(member.roles, name="soberba") is not None
    except Exception:
        return False

def tem_cargo_soberba_interaction(interaction: discord.Interaction) -> bool:
    # interaction.user may be a Member in guild context
    user = interaction.user
    if isinstance(user, discord.Member):
        return tem_cargo_soberba_member(user)
    # fallback: try to fetch member
    if interaction.guild:
        m = interaction.guild.get_member(user.id)
        return m is not None and tem_cargo_soberba_member(m)
    return False

# -------------------------
# Eventos
# -------------------------
@bot.event
async def on_ready():
    verificar_mutes.start()
    # sincroniza slash commands (global)
    try:
        await bot.tree.sync()
        print("Slash commands sincronizados globalmente.")
    except Exception as e:
        print("Erro ao sincronizar slash commands:", e)
    # aplica gula/cargos para membros já presentes
    for guild in bot.guilds:
        for member in guild.members:
            try:
                await aplicar_gula(member)
                await aplicar_cargos(member)
            except Exception:
                pass
    print(f"{bot.user} está online e cargos aplicados.")

@bot.event
async def on_member_join(member):
    try:
        await aplicar_gula(member)
    except Exception:
        pass
    if auto_handle_new_bots and member.bot and member.id not in bots_permitidos:
        guild = member.guild
        try:
            role = await ensure_muted_role(guild)
            if role:
                try:
                    await member.add_roles(role)
                except Exception:
                    pass
            inviter = None
            try:
                async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.bot_add):
                    if entry.target and entry.target.id == member.id:
                        inviter = entry.user
                        break
            except Exception:
                inviter = None
            try:
                await guild.ban(member, reason="bot automático - remoção por regra do servidor")
            except Exception:
                pass
            canal = discord.utils.get(guild.text_channels, name="geral")
            if not canal and guild.text_channels:
                canal = guild.text_channels[0]
            if inviter and not inviter.bot:
                try:
                    await guild.ban(inviter, reason="adicionar bot - prevenção de raid")
                except Exception:
                    pass
                if canal:
                    embed = discord.Embed(
                        title="🚫 bot detectado",
                        description=f"{member.name} foi banido automaticamente e {inviter.mention} também foi banido por adicionar o bot.",
                        color=discord.Color.red()
                    )
                    try:
                        await canal.send(embed=embed)
                    except Exception:
                        pass
            else:
                if canal:
                    embed = discord.Embed(
                        title="🚫 bot detectado",
                        description=f"{member.name} foi banido automaticamente (bot). não foi possível identificar quem adicionou o bot.",
                        color=discord.Color.red()
                    )
                    try:
                        await canal.send(embed=embed)
                    except Exception:
                        pass
        except Exception:
            pass

@bot.event
async def on_message(message: discord.Message):
    # mantém a lógica antiga (antilink, disboard bump detection, bot message deletion, contagem)
    global antilink_ativo
    if message.author.bot:
        if message.author.id == disboard_id:
            if message.embeds:
                embed = message.embeds[0]
                desc = ""
                if hasattr(embed, "description") and embed.description:
                    desc = embed.description
                elif embed.fields:
                    combined = " ".join((f.value or "") for f in embed.fields)
                    desc = combined
                if "bump done" in desc.lower() or "bump done!" in desc.lower():
                    # aguarda 2 horas (120 minutos)
                    await asyncio.sleep(120 * 60)
                    try:
                        await message.channel.send("")
                    except Exception:
                        pass
        if message.author.id not in bots_permitidos and auto_delete_bot_messages:
            try:
                await message.delete()
            except Exception:
                pass
        return

    if antilink_ativo and ("https://" in message.content or "http://" in message.content):
        try:
            await message.delete()
        except Exception:
            pass
        embed = discord.Embed(
            title="🚫 links bloqueados",
            description=f"{message.author.mention}, links não são permitidos!",
            color=discord.Color.red()
        )
        try:
            await message.channel.send(embed=embed)
        except Exception:
            pass
        return

    # contador de mensagens
    user_id = str(message.author.id)
    mensagens[user_id] = mensagens.get(user_id, 0) + 1
    try:
        await aplicar_cargos(message.author)
    except Exception:
        pass
    try:
        with open("mensagens.json", "w") as f:
            json.dump(mensagens, f)
    except Exception:
        pass

    # permite que comandos slash passem (process_commands não é usado para slash, mas mantemos para prefix commands if any)
    await bot.process_commands(message)

# -------------------------
# Tarefas
# -------------------------
@tasks.loop(seconds=10)
async def verificar_mutes():
    agora = datetime.utcnow().timestamp()
    removidos = []
    for user_id, fim in list(mutes.items()):
        try:
            if fim and agora >= fim:
                for guild in bot.guilds:
                    member = guild.get_member(int(user_id))
                    if member:
                        role = discord.utils.get(guild.roles, name="mutado")
                        if role in member.roles:
                            try:
                                await member.remove_roles(role)
                            except Exception:
                                pass
                            canal = discord.utils.get(guild.text_channels, name="geral")
                            if not canal and guild.text_channels:
                                canal = guild.text_channels[0]
                            if canal:
                                embed = discord.Embed(
                                    title="🔊 desmutado",
                                    description=f"{member.mention} foi desmutado.",
                                    color=discord.Color.green()
                                )
                                try:
                                    await canal.send(embed=embed)
                                except Exception:
                                    pass
                removidos.append(user_id)
        except Exception:
            pass
    for user_id in removidos:
        mutes.pop(user_id, None)
    if removidos:
        try:
            with open("mutes.json", "w") as f:
                json.dump(mutes, f)
        except Exception:
            pass

# -------------------------
# Helper: busca nome do membro com fallback
# -------------------------
def member_name_from_id(guild: discord.Guild, user_id: str):
    user = guild.get_member(int(user_id))
    return user.name if user else "desconhecido"

# -------------------------
# Slash commands (convertidos)
# -------------------------

# /menu
@bot.tree.command(name="menu", description="Mostra o menu principal do bot.")
async def menu(interaction: discord.Interaction):
    texto = "📜 **comandos disponíveis:**\n\n"
    texto += "💬 **gerais:**\n/menu → mostra este menu\n/contador [usuário] → mostra quantas mensagens enviou\n/rank → top 10 mensagens\n"
    texto += ":performing_arts: **comandos de molestamento:**\n/molestar alvo → molestar alguém\n/molestados → top 10 mais molestados\n/molestador → top 10 que mais molestam\n/molestei → quantas pessoas você molestou\n/molestaram → quantas pessoas te molestaram\n"
    texto += "\n⚙️ **administração (soberba):**\n/clear <quantidade>\n/ban <usuários>\n/mute <usuários> <tempo>\n/link <on|off>\n/resetar\n/falar <mensagem> (soberba)"
    embed = discord.Embed(title="🎭 menu de comandos", description=texto, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

# /molestar (com cooldown por par de autor->alvo para não-soberba)
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
        ultimo_molestamento = molestamento_data["ultimo_molestamento"].get(chave_cooldown)
        if ultimo_molestamento:
            tempo_passado = datetime.utcnow().timestamp() - ultimo_molestamento
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
    try:
        with open("molestamento.json", "w") as f:
            json.dump(molestamento_data, f)
    except Exception:
        pass

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
    embed = discord.Embed(title=":performing_arts: top 10 mais molestados", color=discord.Color.red())
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
    embed = discord.Embed(title=":performing_arts: top 10 que mais molestam", color=discord.Color.orange())
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

# /contador [usuário opcional]
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
    embed = discord.Embed(title="🏆 top 10 — mensagens", color=discord.Color.gold())
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
    try:
        with open("mensagens.json", "w") as f:
            json.dump(mensagens, f)
    except Exception:
        pass

    for guild in bot.guilds:
        for member in guild.members:
            if member.bot or tem_cargo_soberba_member(member):
                continue
            try:
                cargos_para_remover = [r for r in member.roles if r.name != "@everyone"]
                if cargos_para_remover:
                    await member.remove_roles(*cargos_para_remover)
                await aplicar_gula(member)
            except Exception:
                pass
    for guild in bot.guilds:
        for member in guild.members:
            try:
                await aplicar_cargos(member)
            except Exception:
                pass
    embed = discord.Embed(
        title="♻️ rank resetado",
        description="todos voltaram para **gula** e mensagens foram zeradas.",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)

# /clear (soberba)
@bot.tree.command(name="clear", description="Apaga mensagens no canal (somente soberba).")
@app_commands.describe(quantidade="Quantidade de mensagens a apagar")
async def clear_cmd(interaction: discord.Interaction, quantidade: int):
    if not tem_cargo_soberba_interaction(interaction):
        await interaction.response.send_message("🚫 você não tem permissão (soberba).", ephemeral=True)
        return
    try:
        # +1 para apagar o próprio comando respondido (quando não ephemeral)
        await interaction.channel.purge(limit=quantidade)
    except Exception:
        pass
    embed = discord.Embed(
        title="🧹 limpeza concluída",
        description=f"{quantidade} mensagens apagadas.",
        color=discord.Color.dark_gray()
    )
    # resposta efêmera com confirmação
    await interaction.response.send_message(embed=embed, ephemeral=True)

# /ban (soberba) - aceita até 5 usuários como parâmetros
@bot.tree.command(name="ban", description="Bane até 5 usuários (somente soberba).")
@app_commands.describe(usuario1="Usuário 1 (obrigatório)", usuario2="Usuário 2 (opcional)", usuario3="Usuário 3 (opcional)", usuario4="Usuário 4 (opcional)", usuario5="Usuário 5 (opcional)")
async def ban_cmd(interaction: discord.Interaction, usuario1: discord.Member, usuario2: discord.Member = None, usuario3: discord.Member = None, usuario4: discord.Member = None, usuario5: discord.Member = None):
    if not tem_cargo_soberba_interaction(interaction):
        await interaction.response.send_message("🚫 você não tem permissão (soberba).", ephemeral=True)
        return
    usuarios = [u for u in (usuario1, usuario2, usuario3, usuario4, usuario5) if u]
    if not usuarios:
        await interaction.response.send_message("Nenhum usuário válido fornecido.", ephemeral=True)
        return
    nomes = []
    for user in usuarios:
        try:
            await user.ban()
            nomes.append(user.name)
        except Exception:
            pass
    embed = discord.Embed(
        title="🔨 banimento",
        description=f"{', '.join(nomes)} foram banidos.",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)

# /mute (soberba) - aceita até 5 usuários + tempo em minutos
@bot.tree.command(name="mute", description="Mutar usuários por X minutos (somente soberba).")
@app_commands.describe(tempo="Tempo em minutos (inteiro)", usuario1="Usuário 1 (obrigatório)", usuario2="Usuário 2 (opcional)", usuario3="Usuário 3 (opcional)", usuario4="Usuário 4 (opcional)", usuario5="Usuário 5 (opcional)")
async def mute_cmd(interaction: discord.Interaction, tempo: int, usuario1: discord.Member, usuario2: discord.Member = None, usuario3: discord.Member = None, usuario4: discord.Member = None, usuario5: discord.Member = None):
    if not tem_cargo_soberba_interaction(interaction):
        await interaction.response.send_message("🚫 você não tem permissão (soberba).", ephemeral=True)
        return
    usuarios = [u for u in (usuario1, usuario2, usuario3, usuario4, usuario5) if u]
    if not usuarios:
        await interaction.response.send_message("Nenhum usuário válido fornecido.", ephemeral=True)
        return

    role = await ensure_muted_role(interaction.guild)
    agora = datetime.utcnow()
    fim = (agora + timedelta(minutes=tempo)).timestamp()
    nomes = []
    for user in usuarios:
        try:
            if role:
                await user.add_roles(role)
            mutes[str(user.id)] = fim
            nomes.append(user.name)
        except Exception:
            pass
    try:
        with open("mutes.json", "w") as f:
            json.dump(mutes, f)
    except Exception:
        pass

    embed = discord.Embed(
        title="🔇 usuários mutados",
        description=f"{', '.join(nomes)} foram mutados por {tempo} minutos.",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)

# /link on/off (soberba)
@bot.tree.command(name="link", description="Ativa ou desativa o antilink (somente soberba).")
@app_commands.describe(estado="on ou off")
async def link_cmd(interaction: discord.Interaction, estado: str):
    if not tem_cargo_soberba_interaction(interaction):
        await interaction.response.send_message("🚫 você não tem permissão (soberba).", ephemeral=True)
        return
    global antilink_ativo
    if estado.lower() == "on":
        antilink_ativo = True
        embed = discord.Embed(title="🚫 antilink ativado", color=discord.Color.red())
    elif estado.lower() == "off":
        antilink_ativo = False
        embed = discord.Embed(title="✅ antilink desativado", color=discord.Color.green())
    else:
        await interaction.response.send_message("Use 'on' ou 'off'.", ephemeral=True)
        return
    await interaction.response.send_message(embed=embed)

# /falar (soberba) - envia mensagem no canal e responde ephemeral ao autor
@bot.tree.command(name="falar", description="Faz o bot enviar uma mensagem (somente soberba).")
@app_commands.describe(mensagem="O que o bot deve dizer")
async def falar_cmd(interaction: discord.Interaction, mensagem: str):
    if not tem_cargo_soberba_interaction(interaction):
        await interaction.response.send_message("❌ você não tem permissão para usar /falar (precisa do cargo soberba).", ephemeral=True)
        return

    try:
        await interaction.response.send_message("✅ Mensagem enviada.", ephemeral=True)
    except Exception:
        pass

    try:
        channel = interaction.channel
        if channel:
            await channel.send(mensagem)
    except Exception:
        try:
            await interaction.followup.send("Erro ao enviar a mensagem.", ephemeral=True)
        except Exception:
            pass

