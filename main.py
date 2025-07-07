import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import asyncio
from datetime import datetime, timedelta

# .env 로드
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("❌ DISCORD_TOKEN을 .env 파일에서 불러오지 못했습니다!")
    exit(1)
else:
    print("✅ DISCORD_TOKEN 정상 로드됨")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 서버 ID
YOUR_GUILD_ID = 1388092210519605361

# 채널/역할 ID
ROLE_SELECT_CHANNEL_ID = 1388211020576587786
PARTY_RECRUIT_CHANNEL_ID = 1388112858365300836
WELCOME_CHANNEL_ID = 1390643886656847983
AUTH_ROLE_ID = 1390356825454416094

ROLE_IDS = {
    "세이크리드 가드": 1388109175703470241,
    "다크 메이지": 1388109120141262858,
    "세인트 바드": 1388109253000036384,
    "블래스트 랜서": 1388109274315489404,
    "엘레멘탈 나이트": 1388109205453537311,
    "알케믹 스팅어": 1389897468761870428,
    "포비든 알케미스트": 1389897592061558908,
    "배리어블 거너": 1389897731463581736,
}

party_infos = {}

class RoleToggleButton(Button):
    def __init__(self, role_name, emoji):
        super().__init__(label=role_name, style=discord.ButtonStyle.secondary, emoji=emoji)
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        role = guild.get_role(ROLE_IDS[self.role_name])
        member = interaction.user
        if role in member.roles:
            await member.remove_roles(role)
            await interaction.response.send_message(f"'{self.role_name}' 역할이 제거되었습니다.", ephemeral=True)
        else:
            await member.add_roles(role)
            await interaction.response.send_message(f"'{self.role_name}' 역할이 추가되었습니다.", ephemeral=True)

class RoleSelectView(View):
    def __init__(self):
        super().__init__(timeout=None)
        emoji_map = {
            "세이크리드 가드": "🛡️", "다크 메이지": "🔮", "세인트 바드": "🎵",
            "블래스트 랜서": "⚔️", "엘레멘탈 나이트": "🗡️", "알케믹 스팅어": "🧪",
            "포비든 알케미스트": "☠️", "배리어블 거너": "🔫"
        }
        for role_name in ROLE_IDS:
            self.add_item(RoleToggleButton(role_name, emoji_map[role_name]))

class PartyRoleSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=role, emoji=emoji)
            for role, emoji in zip(ROLE_IDS.keys(), ["🛡️", "🔮", "🎵", "⚔️", "🗡️", "🧪", "☠️", "🔫"])
        ] + [discord.SelectOption(label="참여 취소", emoji="❌")]
        super().__init__(placeholder="직업을 선택하거나 참여 취소하세요!", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        thread_id = interaction.channel.id
        if thread_id not in party_infos:
            return await interaction.response.send_message("⚠️ 파티 정보를 찾을 수 없습니다.", ephemeral=True)

        info = party_infos[thread_id]
        user = interaction.user
        selected = self.values[0]

        if selected == "참여 취소":
            info["participants"].pop(user, None)
            await interaction.response.send_message("파티 참여가 취소되었습니다.", ephemeral=True)
        else:
            info["participants"][user] = selected
            await interaction.response.send_message(f"'{selected}' 역할로 파티에 참여했습니다!", ephemeral=True)

        await update_party_embed(thread_id)

class PartyEditButton(Button):
    def __init__(self):
        super().__init__(label="✏️ 파티 정보 수정", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        thread_id = interaction.channel.id
        if thread_id not in party_infos:
            return await interaction.response.send_message("⚠️ 파티 정보를 찾을 수 없습니다.", ephemeral=True)

        info = party_infos[thread_id]
        if interaction.user != info.get("owner"):
            return await interaction.response.send_message("⛔ 당신은 이 파티의 모집자가 아닙니다.", ephemeral=True)

        await interaction.response.send_message(
            "새로운 파티 정보를 입력해주세요. 예: `던전명 날짜 시간` (예: 브리레흐1-3관 7/10 20:30)",
            ephemeral=True
        )

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            msg = await bot.wait_for("message", timeout=60.0, check=check)
            dungeon, date, time = msg.content.strip().split()

            year = datetime.now().year
            dt_str = f"{year}-{date} {time}"
            party_time = datetime.strptime(dt_str, "%Y-%m/%d %H:%M")
            reminder_time = party_time - timedelta(minutes=30)

            info.update({
                "dungeon": dungeon,
                "date": date,
                "time": time,
                "reminder_time": reminder_time,
            })

            await update_party_embed(thread_id)
            await interaction.followup.send("✅ 파티 정보가 성공적으로 수정되었습니다!", ephemeral=True)

        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ 시간 초과로 수정이 취소되었습니다.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ 오류 발생: {e}", ephemeral=True)

class PartyView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PartyRoleSelect())
        self.add_item(PartyEditButton())

async def update_party_embed(thread_id):
    info = party_infos[thread_id]
    desc_lines = [
        f"📍 던전: **{info['dungeon']}**",
        f"📅 날짜: **{info['date']}**",
        f"⏰ 시간: **{info['time']}**",
        "",
        "**🧑‍🤝‍🧑 현재 참여자 명단:**",
    ]

    main = list(info["participants"].items())[:8]
    reserve = list(info["participants"].items())[8:]

    if main:
        for member, role in main:
            desc_lines.append(f"- {member.display_name}: {role}")
    else:
        desc_lines.append("(아직 없음)")

    if reserve:
        desc_lines.append("\n**📄 예비 인원:**")
        for member, role in reserve:
            desc_lines.append(f"- {member.display_name}: {role}")

    embed = discord.Embed(title="🎯 파티 모집중!", description="\n".join(desc_lines), color=0x00ff00)
    await info["embed_msg"].edit(embed=embed)

@bot.command()
async def 모집(ctx):
    def check(m): return m.author == ctx.author and m.channel == ctx.channel

    await ctx.send("📥 파티 정보를 한 줄로 입력해주세요. 예: `브리레흐1-3관 7/6 20:00`")
    msg = await bot.wait_for("message", timeout=30.0, check=check)
    dungeon, date, time = msg.content.strip().split()

    year = datetime.now().year
    dt_str = f"{year}-{date} {time}"
    party_time = datetime.strptime(dt_str, "%Y-%m/%d %H:%M")
    reminder_time = party_time - timedelta(minutes=30)

    thread = await ctx.channel.create_thread(
        name=f"{ctx.author.display_name}님의 파티 모집",
        type=discord.ChannelType.public_thread,
        auto_archive_duration=60,
    )

    party_infos[thread.id] = {
        "dungeon": dungeon,
        "date": date,
        "time": time,
        "reminder_time": reminder_time,
        "participants": {},
        "embed_msg": None,
        "owner": ctx.author,
    }

    initial = (
        f"📍 던전: **{dungeon}**\n📅 날짜: **{date}**\n⏰ 시간: **{time}**\n\n"
        "**🧑‍🤝‍🧑 현재 참여자 명단:**\n(아직 없음)\n\n"
        "🔔 참여자에게 시작 30분 전에 알림이 전송됩니다!\n"
        "👇 아래 셀렉트 메뉴에서 역할을 선택해 파티에 참여하세요! 최대 8명 + 예비 인원 허용."
    )
    embed = discord.Embed(title="🎯 파티 모집중!", description=initial, color=0x00ff00)
    embed_msg = await thread.send(embed=embed)
    await embed_msg.pin()
    party_infos[thread.id]["embed_msg"] = embed_msg

    await thread.send(view=PartyView())
    await ctx.send(f"{ctx.author.mention}님, 파티 모집 스레드가 생성되었습니다: {thread.mention}")

async def reminder_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now()
        for thread_id, info in list(party_infos.items()):
            reminder_time = info.get("reminder_time")
            if reminder_time and now >= reminder_time:
                participants = info.get("participants", {})
                if participants:
                    mentions = " ".join(m.mention for m in participants)
                    thread = bot.get_channel(thread_id)
                    if thread:
                        try:
                            await thread.send(
                                f"⏰ **리마인더 알림!**\n{mentions}\n"
                                f"`{info['dungeon']}` 던전이 30분 후에 시작됩니다!"
                            )
                            info["reminder_time"] = None
                        except Exception as e:
                            print(f"리마인더 전송 실패 (스레드 {thread_id}): {e}")
        await asyncio.sleep(60)

@bot.event
async def on_ready():
    print(f"✅ 봇 로그인 완료: {bot.user}")
    guild = bot.get_guild(YOUR_GUILD_ID)
    if guild:
        try:
            await guild.me.edit(nick="찡긋봇")
        except Exception as e:
            print(f"닉네임 변경 실패: {e}")
    bot.loop.create_task(reminder_loop())

bot.run(TOKEN)
