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
VERIFY_CHANNEL_ID = 1391373955507552296    # 인증 버튼 메시지를 보낼 채널
VERIFIED_ROLE_ID = 1390356825454416094       # 인증 완료 역할
VERIFY_LOG_CHANNEL_ID = 1391756822763012190    # 인증 로그 채널

# 역할 ID 목록 (직업 역할 + MBTI 역할)
# ROLE_IDS를 직업과 MBTI로 분리하여 관리 (더 명확해짐)
ROLE_IDS = {
    "JOB": {
        "세이크리드 가드": 1388109175703470241,
        "다크 메이지": 1388109120141262858,
        "세인트 바드": 1388109253000036384,
        "블래스트 랜서": 1388109274315489404,
        "엘레멘탈 나이트": 1388109205453537311,
        "알케믹 스팅어": 1389897468761870428,
        "포비든 알케미스트": 1389897592061558908,
        "배리어블 거너": 1389897731463581736,
    },
    "MBTI": {
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
}

# 모든 역할 이름 통합 (RoleSelectView에서 사용)
ALL_ROLE_NAMES = {k: v for category in ROLE_IDS.values() for k, v in category.items()}

# MBTI 역할 이름만 따로 리스트로 정의 (통계 계산 및 단일 선택 처리 시 유용)
MBTI_ROLE_NAMES = list(ROLE_IDS["MBTI"].keys())


DATA_FILE = "data.json"
state = {"role_message_id": None, "party_infos": {}, "initial_message_id": None}

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
                    "party_infos": loaded.get("party_infos", {}),
                    "initial_message_id": loaded.get("initial_message_id") # 초기 메시지 ID 로드
                }
            except Exception as e:
                print(f"state 로드 실패: {e}")

# === 인텐트 및 봇 초기화 ===
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# === 역할 선택 UI 개선: 아르카나/MBTI 탭 ===

# 역할 버튼 이모지 맵
EMOJI_MAP = {
    "세이크리드 가드": "🛡️", "다크 메이지": "🔮", "세인트 바드": "🎵",
    "블래스트 랜서": "⚔️", "엘레멘탈 나이트": "🗡️", "알케믹 스팅어": "🧪",
    "포비든 알케미스트": "☠️", "배리어블 거너": "🔫",
    "ISTJ": "🧱", "ISFJ": "💖", "INFJ": "💡", "INTJ": "🧠",
    "ISTP": "🛠️", "ISFP": "🎨", "INFP": "🌸", "INTP": "🤔",
    "ESTP": "⚡", "ESFP": "🥳", "ENFP": "🌈", "ENTP": "💡",
    "ESTJ": "🏛️", "ESFJ": "🤝", "ENFJ": "🌟", "ENTJ": "👑",
}

class RoleSelectButton(Button):
    def __init__(self, role_name, emoji, role_type):
        # custom_id를 role_type과 role_name을 조합하여 고유하게 만듭니다.
        # 지속성 뷰를 위해 모든 버튼에 고유한 custom_id 필수
        super().__init__(
            label=role_name, 
            style=discord.ButtonStyle.secondary, 
            emoji=emoji, 
            custom_id=f"{role_type}_{role_name}_button" # 고유 custom_id 추가
        )
        self.role_name = role_name
        self.role_type = role_type # "JOB" 또는 "MBTI"

    async def callback(self, interaction: discord.Interaction):
        role_id = ROLE_IDS[self.role_type].get(self.role_name)
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
            if self.role_type == "MBTI":
                for existing_role in interaction.user.roles:
                    if existing_role.name in MBTI_ROLE_NAMES:
                        await interaction.user.remove_roles(existing_role)
                        break # MBTI 역할은 하나만 제거하면 됨
            
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"'{self.role_name}' 역할이 추가되었습니다.", ephemeral=True)


class CategorySelectView(View):
    """아르카나/MBTI 카테고리를 선택하는 초기 뷰"""
    def __init__(self):
        super().__init__(timeout=None) # 봇 재시작 시에도 유지되도록 timeout=None

    @discord.ui.button(label="아르카나 선택", style=discord.ButtonStyle.primary, custom_id="job_select_button", emoji="💫")
    async def job_select_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="👇 원하는 **아르카나 역할**을 선택하거나, `MBTI 선택` 버튼을 눌러주세요.",
            view=RoleButtonsView("JOB") # JOB 카테고리의 역할을 표시
        )

    @discord.ui.button(label="MBTI 선택", style=discord.ButtonStyle.success, custom_id="mbti_select_button", emoji="🎭")
    async def mbti_select_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="👇 원하는 **MBTI 역할**을 선택하거나, `아르카나 선택` 버튼을 눌러주세요.",
            view=RoleButtonsView("MBTI") # MBTI 카테고리의 역할을 표시
        )

class RoleButtonsView(View):
    """선택된 카테고리(아르카나 또는 MBTI)에 해당하는 역할 버튼들을 보여주는 뷰"""
    def __init__(self, role_category: str):
        super().__init__(timeout=None) # 이 뷰도 지속성 뷰로 사용될 수 있도록 timeout=None
        self.role_category = role_category
        
        roles_to_display = ROLE_IDS[self.role_category]

        # 버튼 추가
        for role_name in roles_to_display.keys(): # ROLE_IDS에서 직접 role_name 가져옴
            self.add_item(RoleSelectButton(role_name, EMOJI_MAP.get(role_name, "❓"), self.role_category))
        
        # '뒤로가기' 버튼 추가
        self.add_item(BackToCategoryButton())

class BackToCategoryButton(Button):
    """카테고리 선택 뷰로 돌아가는 버튼"""
    def __init__(self):
        super().__init__(label="🔙 뒤로가기", style=discord.ButtonStyle.danger, row=4, custom_id="back_to_category_button") # custom_id 추가
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="👇 아래 버튼을 눌러 `아르카나` 또는 `MBTI` 역할을 선택하세요!",
            view=CategorySelectView() # 초기 카테고리 선택 뷰로 돌아감
        )

# === 인증 버튼 ===
class VerifyButton(Button):
    def __init__(self, label="✅ 인증하죠", style=discord.ButtonStyle.success, emoji="🪪"):
        super().__init__(label=label, style=style, emoji=emoji, custom_id="verify_button") # custom_id 추가

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
        # 직업(아르카나) 역할만 셀렉트 메뉴에 포함
        options = [
            discord.SelectOption(label=role, emoji=EMOJI_MAP.get(role, "❓"))
            for role in ROLE_IDS["JOB"].keys() # JOB 카테고리 사용
        ] + [discord.SelectOption(label="참여 취소", emoji="❌")]
        # custom_id를 Select에도 추가 (필수)
        super().__init__(placeholder="아르카나를 선택하거나 참여 취소하세요!", min_values=1, max_values=1, options=options, custom_id="party_role_select")

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
    def __init__(self, label="✏️ 파티 정보 수정", style=discord.ButtonStyle.primary):
        super().__init__(label=label, style=style, custom_id="party_edit_button") # custom_id 추가

    async def callback(self, interaction: discord.Interaction):
        thread_id = interaction.channel.id
        info = state["party_infos"].get(str(thread_id))
        if not info:
            return await interaction.response.send_message("⚠️ 파티 정보를 찾을 수 없습니다.", ephemeral=True)

        owner_id = info.get("owner_id")
        if interaction.user.id != owner_id:
            return await interaction.response.send_message("⛔ 당신은 이 파티의 모집자가 아닙니다.", ephemeral=True)

        await interaction.response.send_message("새로운 파티 정보를 입력해주세요. 예: `던전명 7/10 20:30`", ephemeral=True)

        def check(m): return m.author == interaction.user and m.channel == interaction.channel

        try:
            msg = await bot.wait_for("message", timeout=60.0, check=check)
            content_parts = msg.content.strip().split()
            if len(content_parts) < 3:
                await interaction.followup.send("⚠️ 입력 형식이 올바르지 않습니다. (예: `던전명 7/10 20:30`)", ephemeral=True)
                return

            dungeon = content_parts[0]
            date = content_parts[1]
            time = content_parts[2]

            year = datetime.now().year
            # 'M/D' 또는 'MM/DD' 형식을 모두 지원하도록 변경
            dt_str = f"{year}-{date} {time}"
            party_time = datetime.strptime(dt_str, "%Y-%m/%d %H:%M")
            reminder_time = party_time - timedelta(minutes=30)

            info.update({"dungeon": dungeon, "date": date, "time": time, "reminder_time": reminder_time.timestamp()})
            save_state()
            await update_party_embed(thread_id)
            await interaction.followup.send("✅ 파티 정보가 성공적으로 수정되었습니다!", ephemeral=True)

        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ 시간 초과로 수정이 취소되었습니다.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("⚠️ 날짜/시간 형식이 올바르지 않습니다. (예: `7/10 20:30`)", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ 오류 발생: {e}", ephemeral=True)

class PartyView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PartyRoleSelect())
        self.add_item(PartyEditButton())

@bot.command()
async def 모집(ctx):
    # DM에서 사용 불가능하게 수정 (guild가 없는 경우)
    if not ctx.guild:
        await ctx.send("이 명령어는 서버 채널에서만 사용할 수 있습니다.")
        return

    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    await ctx.send("📥 파티 정보를 한 줄로 입력해주세요. 예: `브리레흐1-3관 7/6 20:00`")
    
    try:
        msg = await bot.wait_for("message", timeout=30.0, check=check)
        content_parts = msg.content.strip().split()
        if len(content_parts) < 3:
            await ctx.send("⚠️ 입력 형식이 올바르지 않습니다. (예: `던전명 7/6 20:00`)")
            return

        dungeon = content_parts[0]
        date = content_parts[1]
        time = content_parts[2]

        year = datetime.now().year
        dt_str = f"{year}-{date} {time}"
        # 현재 연도 확인 (2025-07-08)
        current_year = datetime.now().year 
        try:
            party_time = datetime.strptime(dt_str, "%Y-%m/%d %H:%M")
        except ValueError:
            # 연도를 포함하지 않고 MM/DD 형식만 입력했을 경우 재시도
            try:
                party_time = datetime.strptime(f"{current_year}-{date} {time}", "%Y-%m/%d %H:%M")
            except ValueError:
                # 다음 연도로 넘어갔을 경우 (예: 12월에 다음해 1월 날짜 입력)
                try:
                    party_time = datetime.strptime(f"{current_year + 1}-{date} {time}", "%Y-%m/%d %H:%M")
                except ValueError:
                    raise ValueError("날짜/시간 형식이 올바르지 않습니다.")

        reminder_time = party_time - timedelta(minutes=30)

    except asyncio.TimeoutError:
        await ctx.send("⏰ 시간 초과로 파티 생성이 취소되었습니다.")
        return
    except ValueError as e: # Value Error 메시지를 그대로 전달
        await ctx.send(f"⚠️ {e}")
        return
    except Exception as e:
        await ctx.send(f"⚠️ 파티 정보 입력 중 오류 발생: {e}")
        return

    thread = await ctx.channel.create_thread(
        name=f"{ctx.author.display_name}님의 파티 모집",
        type=discord.ChannelType.public_thread,
        auto_archive_duration=60, # 스레드 비활성화 후 60분 뒤 자동 아카이브
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
            print(f"임베드 수정 실패 (스레드 {thread_id}): {e}")

# ---
## MBTI 통계 기능
@bot.command()
async def mbti통계(ctx):
    """서버 내 MBTI 역할 통계를 보여줍니다."""
    guild = ctx.guild
    if not guild:
        await ctx.send("이 명령어는 서버에서만 사용할 수 있습니다.")
        return

    # MBTI 역할 이름 리스트 활용
    mbti_roles_dict = {name: guild.get_role(ROLE_IDS["MBTI"][name]) for name in MBTI_ROLE_NAMES if name in ROLE_IDS["MBTI"]}
    
    # 유효한 역할만 남기고, None인 역할 제거 (혹시 ID가 잘못되었을 경우 대비)
    mbti_roles_dict = {name: role for name, role in mbti_roles_dict.items() if role}

    if not mbti_roles_dict:
        await ctx.send("서버에 설정된 MBTI 역할이 없습니다. `ROLE_IDS['MBTI']` 또는 `MBTI_ROLE_NAMES`를 확인해주세요.")
        return

    # MBTI별 사용자 수 카운트
    mbti_counts = {name: 0 for name in MBTI_ROLE_NAMES}
    
    # 모든 멤버를 가져와 역할을 확인
    members = []
    async for member in guild.fetch_members(limit=None):
        members.append(member)

    for member in members:
        for role in member.roles:
            if role.name in mbti_counts:
                mbti_counts[role.name] += 1
    
    # 통계를 사용자 수가 많은 순서로 정렬
    sorted_mbti_counts = sorted(mbti_counts.items(), key=lambda item: item[1], reverse=True)

    # 임베드 생성
    embed = discord.Embed(
        title="📊 서버 MBTI 통계",
        description="현재 서버 멤버들의 MBTI 역할 분포입니다.",
        color=0x7289DA
    )

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

    role_id = ROLE_IDS["MBTI"].get(mbti_type) # MBTI 딕셔너리에서 ID 가져오기
    if not role_id:
        await ctx.send(f"'{mbti_type}' 역할 ID를 `ROLE_IDS['MBTI']`에서 찾을 수 없습니다. 설정을 확인해주세요.")
        return

    mbti_role = ctx.guild.get_role(role_id)
    if not mbti_role:
        await ctx.send(f"'{mbti_type}' 역할이 서버에 존재하지 않습니다. `ROLE_IDS` 설정을 확인해주세요.")
        return

    members_with_role = []
    # 모든 멤버를 가져와 해당 역할을 가진 멤버를 찾습니다.
    async for member in ctx.guild.fetch_members(limit=None):
        if mbti_role in member.roles:
            members_with_role.append(member.display_name)
    
    embed = discord.Embed(
        title=f"👥 {mbti_type} 유형 멤버 목록",
        color=0x7289DA
    )

    if members_with_role:
        description_text = "\n".join(members_with_role)
        if len(description_text) > 1900: # 디스코드 임베드 설명 최대 길이는 4096자이지만, 안전하게 1900자 정도로 제한
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
        # party_infos 딕셔너리를 복사하여 순회 중 수정되는 것을 방지
        for thread_id_str, info in list(state["party_infos"].items()):
            reminder_time = info.get("reminder_time")
            if reminder_time and now >= reminder_time:
                guild = bot.get_guild(YOUR_GUILD_ID)
                if not guild: # 길드를 찾을 수 없으면 다음 파티로
                    print(f"경고: 길드 ID {YOUR_GUILD_ID}를 찾을 수 없습니다. (리마인더 루프)")
                    continue

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
                        # 알림 후에는 reminder_time을 초기화하여 다시 알림이 가지 않도록 함
                        info["reminder_time"] = None
                        save_state()
                    except Exception as e:
                        print(f"리마인더 전송 실패 (스레드 {thread_id_str}): {e}")
                else:
                    print(f"경고: 스레드 ID {thread_id_str}를 찾을 수 없습니다. (리마인더 루프)")
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

        # 역할 선택 메시지 초기화 및 유지 관리
        role_channel = guild.get_channel(ROLE_SELECT_CHANNEL_ID)
        if role_channel:
            # 봇이 재시작될 때 기존 뷰를 다시 등록
            bot.add_view(CategorySelectView()) # 카테고리 선택 뷰 등록 (직업/MBTI 선택)
            # RoleButtonsView는 메시지 edit_message 시에 생성되므로 여기서 직접 add_view 할 필요 없음
            bot.add_view(VerifyView()) # 인증 뷰 등록 (봇 재시작 시에도 유지)
            bot.add_view(PartyView()) # 파티 모집 뷰 등록 (봇 재시작 시에도 유지)

            # initial_message_id가 저장되어 있는지 확인
            if state["initial_message_id"]:
                try:
                    # 저장된 메시지 ID로 메시지를 가져옴
                    initial_msg = await role_channel.fetch_message(state["initial_message_id"])
                    # 메시지가 존재하면 뷰를 다시 연결 (메시지 내용을 바꾸지 않아도 뷰만 새로 연결 가능)
                    # 만약 메시지 내용도 항상 최신으로 하고 싶다면 content 인자도 추가
                    await initial_msg.edit(view=CategorySelectView()) 
                    print(f"✅ 기존 역할 선택 초기 메시지 ({state['initial_message_id']})에 뷰 재등록 완료.")
                except discord.NotFound:
                    print(f"⚠️ 저장된 역할 선택 초기 메시지 ({state['initial_message_id']})를 찾을 수 없습니다. 새로 전송합니다.")
                    state["initial_message_id"] = None # 메시지가 없으므로 ID 초기화
                    save_state()
                except Exception as e:
                    print(f"역할 선택 초기 메시지 확인 중 오류 발생: {e}")
                    state["initial_message_id"] = None # 오류 발생 시 ID 초기화
                    save_state()

            # 메시지가 없거나, 찾을 수 없어서 ID가 초기화된 경우에만 새로 보냄
            if not state["initial_message_id"]:
                try:
                    # 초기 카테고리 선택 메시지 전송
                    msg = await role_channel.send(
                        "👇 아래 버튼을 눌러 `아르카나` 또는 `MBTI` 역할을 선택하세요!", # '직업'을 '아르카나'로 변경
                        view=CategorySelectView()
                    )
                    state["initial_message_id"] = msg.id
                    save_state()
                    print(f"✅ 새로운 역할 선택 초기 메시지 ({msg.id}) 전송 완료.")
                except Exception as e:
                    print(f"역할 선택 초기 메시지 전송 오류: {e}")

        # 인증 메시지 초기화 및 유지 관리
        verify_channel = guild.get_channel(VERIFY_CHANNEL_ID)
        if verify_channel:
            # 이전에 보낸 인증 메시지가 있다면 찾아서 뷰를 재연결
            # 여기서는 편의상 "인증 메시지"라는 고정된 메시지 ID를 state에 저장하지 않고,
            # 채널의 마지막 메시지를 확인하는 방법을 시도하거나 (불확실성 높음),
            # 아니면 아예 매번 새로 보내도록 유지할 수 있습니다.
            # 현재는 매번 새로 보내는 방식이므로, 중복 방지를 원한다면 initial_message_id와 유사한 로직이 필요합니다.
            
            # 현재 코드 유지 (항상 새로 보내기)
            try:
                # 채널의 최신 5개 메시지 중 봇이 보낸 인증 메시지가 있는지 확인하여 중복 방지 (완벽하진 않음)
                # 이 로직은 간단한 예시이며, 완벽한 중복 방지를 위해서는 initial_message_id와 같은 별도의 상태 관리가 필요합니다.
                found_existing_verify_msg = False
                async for msg_history in verify_channel.history(limit=5):
                    if msg_history.author == bot.user and "✅ 서버에 오신 걸 환영합니다!" in msg_history.content:
                        found_existing_verify_msg = True
                        print("✅ 기존 인증 메시지 발견. 뷰 재등록 시도.")
                        try:
                            # 기존 메시지에 뷰만 다시 연결
                            await msg_history.edit(view=VerifyView())
                            print("✅ 기존 인증 메시지에 뷰 재등록 완료.")
                        except Exception as e_edit:
                            print(f"기존 인증 메시지 수정 중 오류 발생: {e_edit}")
                        break
                
                if not found_existing_verify_msg:
                    await verify_channel.send(
                        "✅ 서버에 오신 걸 환영합니다!\n아래 버튼을 눌러 인증을 완료해주세요.",
                        view=VerifyView()
                    )
                    print("✅ 새로운 인증 메시지 전송 완료.")
            except Exception as e:
                print(f"인증 메시지 전송 오류: {e}")


    # 리마인더 루프 시작
    bot.loop.create_task(reminder_loop())

# === 시작 ===
load_state() # 봇 실행 전 상태 로드
bot.run(TOKEN)