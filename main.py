import os
import json
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord.ui import Button, View, Select

# === .env 로드 ===
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("❌ DISCORD_TOKEN을 .env 파일에서 불러오지 못했습니다!")
    exit(1)
else:
    print("✅ DISCORD_TOKEN 정상 로드됨")

# === 설정 ===
YOUR_GUILD_ID = 1388092210519605361
ROLE_SELECT_CHANNEL_ID = 1388211020576587786
VERIFY_CHANNEL_ID = 1391373955507552296   # 인증 버튼 메시지를 보낼 채널
VERIFIED_ROLE_ID = 1390356825454416094      # 인증 완료 역할
VERIFY_LOG_CHANNEL_ID = 1391756822763012190   # 인증 로그 채널

# 역할 ID 목록 (직업 역할 + MBTI 역할)
ROLE_IDS = {
    # 직업 역할
    "세이크리드 가드": 1388109175703470241,
    "다크 메이지": 1388109120141262858,
    "세인트 바드": 1388109253000036384,
    "블래스트 랜서": 1388109274315489404,
    "엘레멘탈 나이트": 1388109205453537311,
    "알케믹 스팅어": 1389897468761870428,
    "포비든 알케미스트": 1389897592061558908,
    "배리어블 거너": 1389897731463581736,
    # MBTI 역할 추가
    "ISTJ": 1391719641327599717,
    "ISFJ": 1391789705716306063,
    "INFJ": 1391789913942524095,
    "INTJ": 1391788061448208524,
    "ISTP": 1392017470323298334,
    "ISFP": 1391789971702288536,
    "INFP": 1391715412504350730,
    "INTP": 1391790057798504570,
    "ESTP": 1391790142464987156,
    "ESFP": 1391790201902334133,
    "ENFP": 1391790284131532800,
    "ENTP": 1391790424829722794,
    "ESTJ": 1391790662554484906,
    "ESFJ": 1391790746016682056,
    "ENFJ": 1391719175600345180,
    "ENTJ": 1391790926036209835,
}

# MBTI 역할 이름만 따로 리스트로 정의 (통계 계산 시 유용)
MBTI_ROLE_NAMES = [
    "ISTJ", "ISFJ", "INFJ", "INTJ", "ISTP", "ISFP", "INFP", "INTP",
    "ESTP", "ESFP", "ENFP", "ENTP", "ESTJ", "ESFJ", "ENFJ", "ENTJ"
]


DATA_FILE = "data.json"
state = {"role_message_id": None, "party_infos": {}}

# === 상태 로드 및 저장 ===
def save_state():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=4)

def load_state():
    global state
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                loaded = json.load(f)
                state = {
                    "role_message_id": loaded.get("role_message_id"),
                    "party_infos": loaded.get("party_infos", {})
                }
            except Exception as e:
                print(f"state 로드 실패: {e}")

# === 인텐트 및 봇 초기화 ===
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# === 역할 선택 ===
class RoleToggleButton(Button):
    def __init__(self, role_name, emoji):
        super().__init__(label=role_name, style=discord.ButtonStyle.secondary, emoji=emoji)
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction):
        role_id = ROLE_IDS.get(self.role_name)
        if not role_id:
            await interaction.response.send_message(f"'{self.role_name}' 역할 ID를 찾을 수 없습니다.", ephemeral=True)
            return

        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message(f"'{self.role_name}' 역할을 서버에서 찾을 수 없습니다.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"'{self.role_name}' 역할이 제거되었습니다.", ephemeral=True)
        else:
            # MBTI 역할은 한 번에 하나만 가질 수 있도록 처리
            if self.role_name in MBTI_ROLE_NAMES:
                for existing_role in interaction.user.roles:
                    if existing_role.name in MBTI_ROLE_NAMES:
                        await interaction.user.remove_roles(existing_role)
                        break # MBTI 역할은 하나만 제거하면 됨
            
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"'{self.role_name}' 역할이 추가되었습니다.", ephemeral=True)

class RoleSelectView(View):
    def __init__(self):
        super().__init__(timeout=None)
        # 직업 및 MBTI 이모지 매핑
        emoji_map = {
            "세이크리드 가드": "🛡️", "다크 메이지": "🔮", "세인트 바드": "🎵",
            "블래스트 랜서": "⚔️", "엘레멘탈 나이트": "🗡️", "알케믹 스팅어": "🧪",
            "포비든 알케미스트": "☠️", "배리어블 거너": "🔫",
            # MBTI 이모지 (원하는 이모지로 변경 가능)
            "ISTJ": "🧱", "ISFJ": "💖", "INFJ": "💡", "INTJ": "🧠",
            "ISTP": "🛠️", "ISFP": "🎨", "INFP": "🌸", "INTP": "🤔",
            "ESTP": "⚡", "ESFP": "🥳", "ENFP": "🌈", "ENTP": "💡",
            "ESTJ": "🏛️", "ESFJ": "🤝", "ENFJ": "🌟", "ENTJ": "👑",
        }
        for role_name in ROLE_IDS:
            # ROLE_IDS에 있는 모든 역할에 대해 버튼 생성
            # emoji_map에 없는 역할은 기본 이모지 '❓' 사용
            self.add_item(RoleToggleButton(role_name, emoji_map.get(role_name, "❓")))

# === 인증 버튼 ===
class VerifyButton(Button):
    def __init__(self):
        super().__init__(label="✅ 인증하죠", style=discord.ButtonStyle.success, emoji="🪪")

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        if role in interaction.user.roles:
            await interaction.response.send_message("이미 인증된 사용자입니다! 😉", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("성공적으로 인증되었어요! 🎉", ephemeral=True)
            log_channel = interaction.guild.get_channel(VERIFY_LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(f"🛂 {interaction.user.mention} 님이 인증되었습니다! (`{interaction.user.name}`)")

class VerifyView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(VerifyButton())

# === 파티 모집 ===
class PartyRoleSelect(Select):
    def __init__(self):
        # 직업 역할만 셀렉트 메뉴에 포함
        options = [
            discord.SelectOption(label=role, emoji=emoji)
            for role, emoji in zip(
                ["세이크리드 가드", "다크 메이지", "세인트 바드", "블래스트 랜서", "엘레멘탈 나이트", "알케믹 스팅어", "포비든 알케미스트", "배리어블 거너"],
                ["🛡️", "🔮", "🎵", "⚔️", "🗡️", "🧪", "☠️", "🔫"]
            )
        ] + [discord.SelectOption(label="참여 취소", emoji="❌")]
        super().__init__(placeholder="직업을 선택하거나 참여 취소하세요!", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        thread_id = interaction.channel.id
        info = state["party_infos"].get(str(thread_id))
        if not info:
            return await interaction.response.send_message("⚠️ 파티 정보를 찾을 수 없습니다.", ephemeral=True)

        user = interaction.user
        selected = self.values[0]

        if selected == "참여 취소":
            info["participants"].pop(str(user.id), None)
            await interaction.response.send_message("파티 참여가 취소되었습니다.", ephemeral=True)
        else:
            info["participants"][str(user.id)] = selected
            await interaction.response.send_message(f"'{selected}' 역할로 파티에 참여했습니다!", ephemeral=True)

        save_state()
        await update_party_embed(thread_id)

class PartyEditButton(Button):
    def __init__(self):
        super().__init__(label="✏️ 파티 정보 수정", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        thread_id = interaction.channel.id
        info = state["party_infos"].get(str(thread_id))
        if not info:
            return await interaction.response.send_message("⚠️ 파티 정보를 찾을 수 없습니다.", ephemeral=True)

        owner_id = info.get("owner_id")
        if interaction.user.id != owner_id:
            return await interaction.response.send_message("⛔ 당신은 이 파티의 모집자가 아닙니다.", ephemeral=True)

        await interaction.response.send_message("새로운 파티 정보를 입력해주세요. 예: `던전명 날짜 시간` (예: 브리레흐1-3관 7/10 20:30)", ephemeral=True)

        def check(m): return m.author == interaction.user and m.channel == interaction.channel

        try:
            msg = await bot.wait_for("message", timeout=60.0, check=check)
            dungeon, date, time = msg.content.strip().split()
            year = datetime.now().year
            dt_str = f"{year}-{date} {time}"
            party_time = datetime.strptime(dt_str, "%Y-%m/%d %H:%M")
            reminder_time = party_time - timedelta(minutes=30)

            info.update({"dungeon": dungeon, "date": date, "time": time, "reminder_time": reminder_time.timestamp()})
            save_state()
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

    party_info = {
        "dungeon": dungeon,
        "date": date,
        "time": time,
        "reminder_time": reminder_time.timestamp(),
        "participants": {},
        "embed_msg_id": None,
        "owner_id": ctx.author.id,
    }

    state["party_infos"][str(thread.id)] = party_info
    save_state()

    initial = (
        f"📍 던전: **{dungeon}**\n📅 날짜: **{date}**\n⏰ 시간: **{time}**\n\n"
        "**🧑‍🤝‍🧑 현재 참여자 명단:**\n(아직 없음)\n\n"
        "🔔 참여자에게 시작 30분 전에 알림이 전송됩니다!\n"
        "👇 아래 셀렉트 메뉴에서 역할을 선택해 파티에 참여하세요! 최대 8명 + 예비 인원 허용."
    )
    embed = discord.Embed(title="🎯 파티 모집중!", description=initial, color=0x00ff00)
    embed_msg = await thread.send(embed=embed)
    await embed_msg.pin()
    party_info["embed_msg_id"] = embed_msg.id
    save_state()
    await thread.send(view=PartyView())
    await ctx.send(f"{ctx.author.mention}님, 파티 모집 스레드가 생성되었습니다: {thread.mention}")

async def update_party_embed(thread_id):
    info = state["party_infos"].get(str(thread_id))
    if not info:
        return

    desc_lines = [
        f"📍 던전: **{info['dungeon']}**",
        f"📅 날짜: **{info['date']}**",
        f"⏰ 시간: **{info['time']}**",
        "",
        "**🧑‍🤝‍🧑 현재 참여자 명단:**",
    ]

    guild = bot.get_guild(YOUR_GUILD_ID)
    participants = info.get("participants", {})
    main, reserve = [], []
    for idx, (user_id_str, role) in enumerate(participants.items()):
        member = guild.get_member(int(user_id_str))
        if not member:
            continue
        (main if idx < 8 else reserve).append((member, role))

    if main:
        desc_lines += [f"- {m.display_name}: {r}" for m, r in main]
    else:
        desc_lines.append("(아직 없음)")

    if reserve:
        desc_lines.append("\n**📄 예비 인원:**")
        desc_lines += [f"- {m.display_name}: {r}" for m, r in reserve]

    embed = discord.Embed(title="🎯 파티 모집중!", description="\n".join(desc_lines), color=0x00ff00)
    channel = bot.get_channel(int(thread_id))
    if channel and info.get("embed_msg_id"):
        try:
            msg = await channel.fetch_message(info["embed_msg_id"])
            await msg.edit(embed=embed)
        except Exception as e:
            print(f"임베드 수정 실패: {e}")
@bot.command()
async def mbti통계(ctx):
    """서버 내 MBTI 역할 통계를 보여줍니다."""
    guild = ctx.guild
    if not guild:
        await ctx.send("이 명령어는 서버에서만 사용할 수 있습니다.")
        return

    # MBTI 역할만 필터링 (MBTI_ROLE_NAMES 리스트 활용)
    mbti_roles = {name: guild.get_role(ROLE_IDS[name]) for name in MBTI_ROLE_NAMES if name in ROLE_IDS}
    
    # 유효한 역할만 남기고, None인 역할 제거 (혹시 ID가 잘못되었을 경우 대비)
    mbti_roles = {name: role for name, role in mbti_roles.items() if role}

    if not mbti_roles:
        await ctx.send("서버에 설정된 MBTI 역할이 없습니다. `ROLE_IDS` 또는 `MBTI_ROLE_NAMES`를 확인해주세요.")
        return

    # MBTI별 사용자 수 카운트
    mbti_counts = {name: 0 for name in MBTI_ROLE_NAMES}
    # 길드 멤버를 순회하며 각 멤버가 가진 역할을 확인
    async for member in guild.fetch_members(limit=None): # 모든 멤버를 가져오기 위해 limit=None 사용
        for role in member.roles:
            if role.name in mbti_counts:
                mbti_counts[role.name] += 1
    
    # 통계를 사용자 수가 많은 순서로 정렬
    sorted_mbti_counts = sorted(mbti_counts.items(), key=lambda item: item[1], reverse=True)

    # 임베드 생성
    embed = discord.Embed(
        title="📊 서버 MBTI 통계",
        description="현재 서버 멤버들의 MBTI 역할 분포입니다.",
        color=0x7289DA  # Discord 기본 색상
    )

    # 필드에 통계 추가
    total_mbti_users = 0
    for mbti, count in sorted_mbti_counts:
        if count > 0: # 0명인 MBTI는 표시하지 않음
            embed.add_field(name=mbti, value=f"{count}명", inline=True)
            total_mbti_users += count
    
    if total_mbti_users == 0:
        embed.description = "아직 MBTI 역할을 선택한 사용자가 없습니다."

    embed.set_footer(text=f"총 MBTI 선택 사용자: {total_mbti_users}명")
    await ctx.send(embed=embed)


@bot.command()
async def mbti확인(ctx, mbti_type: str):
    """특정 MBTI 역할을 가진 멤버 목록을 보여줍니다. (예: !mbti확인 ENFP)"""
    mbti_type = mbti_type.upper() # 입력된 MBTI 유형을 대문자로 변환

    if mbti_type not in MBTI_ROLE_NAMES: # MBTI_ROLE_NAMES에 있는지 확인
        await ctx.send(f"⚠️ '{mbti_type}'는 유효한 MBTI 역할이 아닙니다. 정확한 MBTI 유형을 입력해주세요. (예: ISTJ, ENFP)")
        return

    role_id = ROLE_IDS.get(mbti_type)
    if not role_id:
        await ctx.send(f"'{mbti_type}' 역할 ID를 `ROLE_IDS`에서 찾을 수 없습니다. 설정을 확인해주세요.")
        return

    mbti_role = ctx.guild.get_role(role_id)
    if not mbti_role:
        await ctx.send(f"'{mbti_type}' 역할이 서버에 존재하지 않습니다. `ROLE_IDS` 설정을 확인해주세요.")
        return

    members_with_role = []
    # 길드 멤버를 순회하며 해당 역할을 가진 멤버를 찾습니다.
    async for member in ctx.guild.fetch_members(limit=None): # 모든 멤버를 가져오기 위해 limit=None 사용
        if mbti_role in member.roles:
            members_with_role.append(member.display_name)
    
    embed = discord.Embed(
        title=f"👥 {mbti_type} 유형 멤버 목록",
        color=0x7289DA
    )

    if members_with_role:
        # 멤버가 많을 경우 디스코드 메시지 길이 제한(2000자)을 고려해야 합니다.
        # 여기서는 간단하게 모두 나열하되, 메시지가 너무 길어지면 잘릴 수 있습니다.
        # 실제 운영에서는 페이지네이션 등의 고급 처리가 필요할 수 있습니다.
        description_text = "\n".join(members_with_role)
        if len(description_text) > 1900: # 대략적인 안전선
            description_text = description_text[:1900] + "\n...(이하 생략)"
        embed.description = description_text
        embed.set_footer(text=f"총 {len(members_with_role)}명")
    else:
        embed.description = f"현재 '{mbti_type}' 역할을 가진 멤버가 없습니다."

    await ctx.send(embed=embed)

# === 리마인더 루프 ===
async def reminder_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now().timestamp()
        for thread_id_str, info in list(state["party_infos"].items()):
            reminder_time = info.get("reminder_time")
            if reminder_time and now >= reminder_time:
                guild = bot.get_guild(YOUR_GUILD_ID)
                mentions = []
                for user_id_str in info.get("participants", {}).keys():
                    member = guild.get_member(int(user_id_str))
                    if member:
                        mentions.append(member.mention)
                thread = bot.get_channel(int(thread_id_str))
                if thread:
                    try:
                        await thread.send(
                            f"⏰ **리마인더 알림!**\n{' '.join(mentions)}\n"
                            f"`{info['dungeon']}` 던전이 30분 후에 시작됩니다!"
                        )
                        info["reminder_time"] = None
                        save_state()
                    except Exception as e:
                        print(f"리마인더 전송 실패 (스레드 {thread_id_str}): {e}")
        await asyncio.sleep(60)

# === 봇 실행 시 초기화 ===
@bot.event
async def on_ready():
    print(f"✅ 봇 로그인 완료: {bot.user}")
    guild = bot.get_guild(YOUR_GUILD_ID)

    if guild:
        try:
            await guild.me.edit(nick="찡긋봇")
        except Exception as e:
            print(f"닉네임 변경 실패: {e}")

        role_channel = guild.get_channel(ROLE_SELECT_CHANNEL_ID)
        if role_channel:
            message_exists = False
            if state["role_message_id"]:
                try:
                    # 저장된 메시지 ID가 있으면 해당 메시지를 가져와서 존재하는지 확인
                    await role_channel.fetch_message(state["role_message_id"])
                    message_exists = True
                    print(f"✅ 기존 역할 선택 메시지 ({state['role_message_id']}) 발견.")
                except discord.NotFound:
                    # 메시지가 디스코드에서 삭제된 경우
                    print(f"⚠️ 저장된 역할 선택 메시지 ({state['role_message_id']})를 찾을 수 없습니다. (삭제되었을 가능성)")
                    state["role_message_id"] = None # 메시지가 없으므로 ID 초기화
                    save_state()
                except Exception as e:
                    # 그 외 메시지 확인 중 오류 발생
                    print(f"역할 선택 메시지 확인 중 오류 발생: {e}")
                    state["role_message_id"] = None # 오류 발생 시 ID 초기화
                    save_state()

            # 메시지가 존재하지 않거나, 존재했지만 찾을 수 없어서 ID가 초기화된 경우에만 새로 보냄
            if not message_exists:
                try:
                    msg = await role_channel.send("👇 원하는 직업 또는 MBTI 역할을 선택하세요!", view=RoleSelectView())
                    state["role_message_id"] = msg.id
                    save_state()
                    print(f"✅ 새로운 역할 선택 메시지 ({msg.id}) 전송 완료.")
                except Exception as e:
                    print(f"역할 선택 메시지 전송 오류: {e}")

        verify_channel = guild.get_channel(VERIFY_CHANNEL_ID)
        if verify_channel:
            # 인증 메시지는 매 봇 시작 시 보내도록 유지합니다.
            # 만약 인증 메시지도 한 번만 보내고 싶다면, 역할 선택 메시지와 유사하게 상태를 관리해야 합니다.
            try:
                await verify_channel.send(
                    "✅ 서버에 오신 걸 환영합니다!\n아래 버튼을 눌러 인증을 완료해주세요.",
                    view=VerifyView()
                )
            except Exception as e:
                print(f"인증 메시지 전송 오류: {e}")

    bot.loop.create_task(reminder_loop())

# === 시작 ===
load_state()
bot.run(TOKEN)