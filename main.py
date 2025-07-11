import os
import json
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
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
VERIFIED_ROLE_ID = 1390356825454416094      # 인증 완료 역할 (이 역할이 '찡긋' 역할이 됩니다)
GUEST_ROLE_ID = 1392288019623835686      # '손님' 역할 ID (Discord에서 생성 후 여기에 붙여넣으세요!)
VERIFY_LOG_CHANNEL_ID = 1391756822763012190     # 인증 로그 채널
WELCOME_CHANNEL_ID = 1390643886656847983 # "반갑죠채널"의 실제 채널 ID

# --- 인증 질문/답변 설정 ---
VERIFY_QUESTION = "찡긋 디스코드 채널에 오신것을 환영합니다.\n안내받은 코드를 입력하세요.\n(코드가 없을 경우 승인이 불가합니다.)"
VERIFY_ANSWER = "20211113"
VERIFY_TIMEOUT = 60 # 답변 대기 시간 (초)

# 역할 ID 목록 (직업 역할 + MBTI 역할)
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
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

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
                    if existing_role.name in MBTI_ROLE_NAMES: # MBTI 역할 이름 리스트를 사용하여 체크
                        await interaction.user.remove_roles(existing_role)
                        break
            
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"'{self.role_name}' 역할이 추가되었습니다.", ephemeral=True)


class CategorySelectView(View):
    """아르카나/MBTI 카테고리를 선택하는 초기 뷰"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="아르카나 선택", style=discord.ButtonStyle.primary, custom_id="job_select_button", emoji="💫")
    async def job_select_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="👇 원하는 **아르카나 역할**을 선택하거나, `MBTI 선택` 버튼을 눌러주세요.",
            view=RoleButtonsView("JOB")
        )

    @discord.ui.button(label="MBTI 선택", style=discord.ButtonStyle.success, custom_id="mbti_select_button", emoji="🎭")
    async def mbti_select_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="👇 원하는 **MBTI 역할**을 선택하거나, `아르카나 선택` 버튼을 눌러주세요.",
            view=RoleButtonsView("MBTI")
        )

class RoleButtonsView(View):
    """선택된 카테고리(아르카나 또는 MBTI)에 해당하는 역할 버튼들을 보여주는 뷰"""
    def __init__(self, role_category: str):
        super().__init__(timeout=None)
        self.role_category = role_category
        
        roles_to_display = ROLE_IDS[self.role_category]

        for role_name in roles_to_display.keys():
            self.add_item(RoleSelectButton(role_name, EMOJI_MAP.get(role_name, "❓"), self.role_category))
        
        self.add_item(BackToCategoryButton())

class BackToCategoryButton(Button):
    """카테고리 선택 뷰로 돌아가는 버튼"""
    def __init__(self, ):
        super().__init__(label="🔙 뒤로가기", style=discord.ButtonStyle.danger, row=4, custom_id="back_to_category_button")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="👇 아래 버튼을 눌러 `아르카나` 또는 `MBTI` 역할을 선택하세요!",
            view=CategorySelectView()
        )

# === 인증 버튼 수정: 질문/답변 추가 ===
class VerifyButton(Button):
    def __init__(self, label="✅ 인증하죠", style=discord.ButtonStyle.success, emoji="🪪"):
        super().__init__(label=label, style=style, emoji=emoji, custom_id="verify_button")

    async def callback(self, interaction: discord.Interaction):
        verified_role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        guest_role = interaction.guild.get_role(GUEST_ROLE_ID)

        if verified_role in interaction.user.roles:
            return await interaction.response.send_message("이미 인증된 사용자입니다! 😉", ephemeral=True)

        # DM으로 인증 질문 전송
        try:
            await interaction.user.send(f"**인증 질문:**\n\n{VERIFY_QUESTION}")
            await interaction.response.send_message("DM으로 인증 질문을 보냈습니다. DM을 확인하고 코드를 입력해주세요! ✉️", ephemeral=True)

            def check(m):
                return m.author == interaction.user and m.channel == interaction.user.dm_channel

            try:
                # 사용자의 답변을 기다림 (VERIFY_TIMEOUT 초 동안)
                answer_msg = await bot.wait_for("message", timeout=VERIFY_TIMEOUT, check=check)

                # 답변이 정확한지 확인
                if answer_msg.content.strip() == VERIFY_ANSWER:
                    # 인증 성공 로직
                    await interaction.user.add_roles(verified_role)
                    if guest_role and guest_role in interaction.user.roles:
                        await interaction.user.remove_roles(guest_role)
                    
                    await interaction.user.send("✅ 코드가 확인되었습니다! 성공적으로 인증되었어요! 이제 모든 채널을 이용할 수 있습니다! 🎉")
                    log_channel = interaction.guild.get_channel(VERIFY_LOG_CHANNEL_ID)
                    if log_channel:
                        await log_channel.send(f"🛂 {interaction.user.mention} 님이 **찡긋** 역할로 인증되었습니다! (`{interaction.user.name}`)")
                else:
                    # 답변이 틀렸을 경우
                    await interaction.user.send("❌ 코드가 틀렸습니다. 다시 인증 버튼을 눌러 시도해주세요. 올바른 코드를 확인해주세요.")
            except asyncio.TimeoutError:
                # 시간 초과 시
                await interaction.user.send(f"⏰ {VERIFY_TIMEOUT}초 내에 답변이 없어서 인증이 취소되었습니다. 다시 인증 버튼을 눌러 시도해주세요.")
            except Exception as e:
                # 그 외 예외 처리
                await interaction.user.send(f"인증 중 알 수 없는 오류가 발생했습니다. 잠시 후 다시 시도해주세요. ({e})")
                print(f"인증 DM 답변 처리 중 오류: {e}")

        except discord.Forbidden:
            # DM을 보낼 수 없는 경우 (사용자가 DM을 막아놓았을 때)
            await interaction.response.send_message(
                "DM을 보낼 수 없습니다. 개인정보 설정에서 서버 멤버로부터의 DM을 허용해주세요. "
                "DM 설정 변경 후 다시 인증 버튼을 눌러 시도해주세요.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"인증 질문 전송 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요. ({e})", ephemeral=True)
            print(f"인증 질문 DM 전송 오류: {e}")

class VerifyView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(VerifyButton())

# === 파티 모집 ===
class PartyRoleSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=role, emoji=EMOJI_MAP.get(role, "❓"))
            for role in ROLE_IDS["JOB"].keys()
        ] + [discord.SelectOption(label="참여 취소", emoji="❌")]
        super().__init__(placeholder="아르카나를 선택하거나 참여 취소하세요!", min_values=1, max_values=1, options=options, custom_id="party_role_select")

    async def callback(self, interaction: discord.Interaction):
        thread_id = interaction.channel.id
        info = state["party_infos"].get(str(thread_id))
        if not info:
            return await interaction.response.send_message("⚠️ 파티 정보를 찾을 수 없습니다.", ephemeral=True)

        user = interaction.user
        selected = self.values[0]

        if selected == "참여 취소":
            if str(user.id) in info["participants"]:
                info["participants"].pop(str(user.id), None)
                await interaction.response.send_message("파티 참여가 취소되었습니다.", ephemeral=True)
            else:
                await interaction.response.send_message("아직 이 파티에 참여하지 않았습니다.", ephemeral=True)
        else:
            info["participants"][str(user.id)] = selected
            await interaction.response.send_message(f"'{selected}' 역할로 파티에 참여했습니다!", ephemeral=True)

        save_state()
        await update_party_embed(thread_id)

class PartyEditButton(Button):
    def __init__(self, label="✏️ 파티 정보 수정", style=discord.ButtonStyle.primary):
        super().__init__(label=label, style=style, custom_id="party_edit_button")

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
            date_str = content_parts[1]
            time_str = content_parts[2]

            # 파티 시간 파싱 로직 개선
            current_year = datetime.now().year
            party_time = None
            for year_offset in [0, 1]: # 현재 연도, 다음 연도 시도
                try:
                    # '월/일' 형식을 위해 strptime 형식 변경
                    party_time = datetime.strptime(f"{current_year + year_offset}-{date_str} {time_str}", "%Y-%m/%d %H:%M")
                    # 만약 파싱된 시간이 현재보다 과거라면 다음 연도를 시도 (단, 1년 이상 과거는 아님)
                    if party_time < datetime.now() and year_offset == 0:
                        continue # 다음 연도로 다시 시도
                    break # 성공적으로 파싱했으면 루프 종료
                except ValueError:
                    continue # 파싱 실패 시 다음 연도 시도
            
            if not party_time:
                raise ValueError("날짜/시간 형식이 올바르지 않거나 유효하지 않은 날짜입니다. (예: 7/10 20:30)")

            reminder_time = party_time - timedelta(minutes=30)

            info.update({"dungeon": dungeon, "date": date_str, "time": time_str, "reminder_time": reminder_time.timestamp()})
            save_state()
            await update_party_embed(thread_id)
            await interaction.followup.send("✅ 파티 정보가 성공적으로 수정되었습니다!", ephemeral=True)

        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ 시간 초과로 수정이 취소되었습니다.", ephemeral=True)
        except ValueError as e:
            await interaction.followup.send(f"⚠️ {e}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ 오류 발생: {e}", ephemeral=True)

class PartyView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PartyRoleSelect())
        self.add_item(PartyEditButton())

@bot.command()
async def 모집(ctx):
    if not ctx.guild:
        await ctx.send("이 명령어는 서버 채널에서만 사용할 수 있습니다.")
        return

    # '찡긋' 역할이 없는 사용자에게는 명령어 사용을 제한
    verified_role = ctx.guild.get_role(VERIFIED_ROLE_ID)
    if not verified_role or verified_role not in ctx.author.roles:
        await ctx.send("⛔ 파티 모집은 `찡긋` 역할을 가진 멤버만 가능합니다. 먼저 인증을 완료해주세요!", ephemeral=True)
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
        date_str = content_parts[1]
        time_str = content_parts[2]

        # 파티 시간 파싱 로직 개선
        current_year = datetime.now().year
        party_time = None
        for year_offset in [0, 1]: # 현재 연도, 다음 연도 시도
            try:
                party_time = datetime.strptime(f"{current_year + year_offset}-{date_str} {time_str}", "%Y-%m/%d %H:%M")
                if party_time < datetime.now() and year_offset == 0:
                    continue
                break
            except ValueError:
                continue
        
        if not party_time:
            raise ValueError("날짜/시간 형식이 올바르지 않거나 유효하지 않은 날짜입니다. (예: 7/6 20:00)")

        reminder_time = party_time - timedelta(minutes=30)

    except asyncio.TimeoutError:
        await ctx.send("⏰ 시간 초과로 파티 생성이 취소되었습니다.")
        return
    except ValueError as e:
        await ctx.send(f"⚠️ {e}")
        return
    except Exception as e:
        await ctx.send(f"⚠️ 파티 정보 입력 중 오류 발생: {e}")
        return

    thread = await ctx.channel.create_thread(
        name=f"{ctx.author.display_name}님의 파티 모집",
        type=discord.ChannelType.public_thread,
        auto_archive_duration=60,
    )

    party_info = {
        "dungeon": dungeon,
        "date": date_str,
        "time": time_str,
        "reminder_time": reminder_time.timestamp(),
        "participants": {},
        "embed_msg_id": None,
        "owner_id": ctx.author.id,
    }

    state["party_infos"][str(thread.id)] = party_info
    save_state()

    initial = (
        f"📍 던전: **{dungeon}**\n📅 날짜: **{date_str}**\n⏰ 시간: **{time_str}**\n\n"
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

    mbti_roles_dict = {name: guild.get_role(ROLE_IDS["MBTI"][name]) for name in MBTI_ROLE_NAMES if name in ROLE_IDS["MBTI"]}
    mbti_roles_dict = {name: role for name, role in mbti_roles_dict.items() if role}

    if not mbti_roles_dict:
        await ctx.send("서버에 설정된 MBTI 역할이 없습니다. `ROLE_IDS['MBTI']` 또는 `MBTI_ROLE_NAMES`를 확인해주세요.")
        return

    mbti_counts = {name: 0 for name in MBTI_ROLE_NAMES}
    
    members = []
    async for member in guild.fetch_members(limit=None):
        members.append(member)

    for member in members:
        for role in member.roles:
            if role.name in mbti_counts:
                mbti_counts[role.name] += 1
    
    sorted_mbti_counts = sorted(mbti_counts.items(), key=lambda item: item[1], reverse=True)

    embed = discord.Embed(
        title="📊 서버 MBTI 통계",
        description="현재 서버 멤버들의 MBTI 역할 분포입니다.",
        color=0x7289DA
    )

    total_mbti_users = 0
    for mbti, count in sorted_mbti_counts:
        if count > 0:
            embed.add_field(name=mbti, value=f"{count}명", inline=True)
            total_mbti_users += count
    
    if total_mbti_users == 0:
        embed.description = "아직 MBTI 역할을 선택한 사용자가 없습니다."

    embed.set_footer(text=f"총 MBTI 선택 사용자: {total_mbti_users}명")
    await ctx.send(embed=embed)


@bot.command()
async def mbti확인(ctx, mbti_type: str):
    """특정 MBTI 역할을 가진 멤버 목록을 보여줍니다. (예: !mbti확인 ENFP)"""
    mbti_type = mbti_type.upper()

    if mbti_type not in MBTI_ROLE_NAMES:
        await ctx.send(f"⚠️ '{mbti_type}'는 유효한 MBTI 역할이 아닙니다. 정확한 MBTI 유형을 입력해주세요. (예: ISTJ, ENFP)")
        return

    role_id = ROLE_IDS["MBTI"].get(mbti_type)
    if not role_id:
        await ctx.send(f"'{mbti_type}' 역할 ID를 `ROLE_IDS['MBTI']`에서 찾을 수 없습니다. 설정을 확인해주세요.")
        return

    mbti_role = ctx.guild.get_role(role_id)
    if not mbti_role:
        await ctx.send(f"'{mbti_type}' 역할이 서버에 존재하지 않습니다. `ROLE_IDS` 설정을 확인해주세요.")
        return

    members_with_role = []
    async for member in ctx.guild.fetch_members(limit=None):
        if mbti_role in member.roles:
            members_with_role.append(member.display_name)
    
    embed = discord.Embed(
        title=f"👥 {mbti_type} 유형 멤버 목록",
        color=0x7289DA
    )

    if members_with_role:
        description_text = "\n".join(members_with_role)
        if len(description_text) > 1900:
            description_text = description_text[:1900] + "\n...(이하 생략)"
        embed.description = description_text
        embed.set_footer(text=f"총 {len(members_with_role)}명")
    else:
        embed.description = f"현재 '{mbti_type}' 역할을 가진 멤버가 없습니다."

    await ctx.send(embed=embed)

# ---
## 명령어 도움말 기능
@bot.command(name="도움말", aliases=["help", "명령어"])
async def show_help(ctx):
    """봇의 사용 가능한 명령어 목록을 보여줍니다."""
    
    embed = discord.Embed(
        title="✨ 찡긋봇 명령어 도움말 ✨",
        description="찡긋봇이 제공하는 명령어는 다음과 같습니다:",
        color=0x7289DA
    )

    embed.add_field(
        name="🎉 파티 모집",
        value="`!모집` - 새로운 파티 모집 스레드를 생성합니다.\n(스레드 내에서 파티 참여/수정 버튼 이용)",
        inline=False
    )

    embed.add_field(
        name="📊 MBTI 통계",
        value="`!mbti통계` - 서버 내 MBTI 역할 분포를 보여줍니다.\n"
              "`!mbti확인 [MBTI유형]` - 특정 MBTI 역할을 가진 멤버 목록을 보여줍니다. (예: `!mbti확인 ENFP`)",
        inline=False
    )
    
    embed.add_field(
        name="📌 역할 선택 및 인증",
        value="역할 선택은 <#{ROLE_SELECT_CHANNEL_ID}> 채널에서, 인증은 <#{VERIFY_CHANNEL_ID}> 채널에서 버튼을 통해 진행할 수 있습니다.",
        inline=False
    )

    embed.set_footer(text=f"문의사항은 서버 관리자에게 문의해주세요. | 봇 버전: v0.1")
    embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else discord.Embed.Empty)

    await ctx.send(embed=embed)


# === 리마인더 루프 ===
@tasks.loop(minutes=1) # 1분마다 실행되도록 변경
async def reminder_loop():
    await bot.wait_until_ready() # 봇이 준비될 때까지 대기
    # print("리마인더 루프 실행 중...") # 너무 많이 출력될 수 있어 주석 처리

    now = datetime.now()
    
    # dictionary를 복사하여 반복 중 수정 오류 방지
    for thread_id_str, info in list(state["party_infos"].items()):
        reminder_timestamp = info.get("reminder_time")
        
        if reminder_timestamp is None:
            continue # 이미 알림이 전송되었거나, 리마인더 시간이 설정되지 않은 경우

        reminder_dt = datetime.fromtimestamp(reminder_timestamp)

        # 현재 시간과 리마인더 시간의 차이를 계산
        time_until_reminder = reminder_dt - now
        
        # 리마인더가 발동해야 할 시간 (예: 30분 전)과 현재 시간이 근접한지 확인
        # 0분 ~ 1분 사이 (1분 이내)로 설정하여 정확도를 높임
        if timedelta(minutes=0) <= time_until_reminder <= timedelta(minutes=1):
            guild = bot.get_guild(YOUR_GUILD_ID)
            if not guild:
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
                        f"`{info['dungeon']}` 던전이 30분 후에 시작됩니다! **({info['date']} {info['time']})**"
                    )
                    # 알림을 보냈으니 reminder_time을 제거하거나, 이미 보낸 시간을 기록
                    info["reminder_time"] = None # 다시 알림이 울리지 않도록 None으로 설정
                    save_state()
                    print(f"리마인더 전송 완료: 스레드 {thread_id_str} - {info['dungeon']}")
                except Exception as e:
                    print(f"리마인더 전송 실패 (스레드 {thread_id_str}): {e}")
            else:
                print(f"경고: 스레드 ID {thread_id_str}를 찾을 수 없습니다. (리마인더 루프)")
        
        # 과거 시간인데 리마인더가 아직 남아있는 경우 (봇 재시작 등으로 놓쳤을 경우)
        elif reminder_dt < now and reminder_timestamp is not None:
            # 리마인더 시간을 None으로 설정하여 다시 알림이 울리지 않도록 함
            info["reminder_time"] = None
            save_state()
            # print(f"과거 리마인더 시간 발견 및 처리 (스레드 {thread_id_str}): {info['dungeon']}") # 너무 많이 출력될 수 있어 주석 처리


# === 새 멤버가 서버에 들어올 때 작동하는 함수 추가 ===
@bot.event
async def on_member_join(member):
    guild = member.guild
    if guild.id == YOUR_GUILD_ID: # 봇이 설정된 길드인지 확인
        guest_role = guild.get_role(GUEST_ROLE_ID)
        if guest_role:
            await member.add_roles(guest_role)
            print(f"✅ {member.display_name} 님에게 '손님' 역할 부여 완료.")
        else:
            print(f"⚠️ '손님' 역할 (ID: {GUEST_ROLE_ID})을 찾을 수 없습니다. 역할 ID를 확인해주세요.")

        welcome_channel = guild.get_channel(WELCOME_CHANNEL_ID)
        if welcome_channel:
            # Welcome 메시지 구성 (인증 및 역할 선택 채널 멘션 포함)
            welcome_message = (
                f"{member.mention} 님, 찡긋 길드 디스코드 서버에 오신 것을 환영합니다! ✨\n\n"
                f"저희 서버는 **인증**을 해야 모든 채널을 이용할 수 있습니다. 🧐\n"
                f"현재는 **손님** 역할이 부여되어 일부 채널만 볼 수 있어요.\n\n"
                f"1. 먼저 <#{VERIFY_CHANNEL_ID}> 채널로 이동하여 **`인증하죠`** 버튼을 눌러 **`찡긋`** 멤버가 되어주세요! 🪪\n"
                f"2. 인증 완료 후 <#{ROLE_SELECT_CHANNEL_ID}> 채널에서 **아르카나 및 MBTI 역할**을 선택해주세요! 🎭\n\n"
                "즐거운 시간 되세요! 😄"
            )
            await welcome_channel.send(welcome_message)
            print(f"✅ {member.display_name} 님께 환영 메시지 전송 완료. (채널: {welcome_channel.name})")
        else:
            print(f"⚠️ 환영 메시지를 보낼 채널 (ID: {WELCOME_CHANNEL_ID})을 찾을 수 없습니다. 채널 ID를 확인해주세요.")
    else:
        print(f"⚠️ 봇이 설정된 길드 ({YOUR_GUILD_ID})가 아닌 다른 길드에 멤버가 조인했습니다.")


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

        # 모든 persistent view를 재등록
        bot.add_view(CategorySelectView())
        bot.add_view(VerifyView())
        bot.add_view(PartyView())

        # 역할 선택 메시지 확인 및 재전송
        role_channel = guild.get_channel(ROLE_SELECT_CHANNEL_ID)
        if role_channel:
            if state["initial_message_id"]:
                try:
                    initial_msg = await role_channel.fetch_message(state["initial_message_id"])
                    await initial_msg.edit(view=CategorySelectView())
                    print(f"✅ 기존 역할 선택 초기 메시지 ({state['initial_message_id']})에 뷰 재등록 완료.")
                except discord.NotFound:
                    print(f"⚠️ 저장된 역할 선택 초기 메시지 ({state['initial_message_id']})를 찾을 수 없습니다. 새로 전송합니다.")
                    state["initial_message_id"] = None
                    save_state()
                except Exception as e:
                    print(f"역할 선택 초기 메시지 확인 중 오류 발생: {e}")
                    state["initial_message_id"] = None
                    save_state()

            if not state["initial_message_id"]:
                try:
                    msg = await role_channel.send(
                        "👇 아래 버튼을 눌러 `아르카나` 또는 `MBTI` 역할을 선택하세요!",
                        view=CategorySelectView()
                    )
                    state["initial_message_id"] = msg.id
                    save_state()
                    print(f"✅ 새로운 역할 선택 초기 메시지 ({msg.id}) 전송 완료.")
                except Exception as e:
                    print(f"역할 선택 초기 메시지 전송 오류: {e}")

        # 인증 메시지 확인 및 재전송
        verify_channel = guild.get_channel(VERIFY_CHANNEL_ID)
        if verify_channel:
            try:
                found_existing_verify_msg = False
                async for msg_history in verify_channel.history(limit=5): # 최근 5개 메시지 확인
                    if msg_history.author == bot.user and "✅ 서버에 오신 걸 환영합니다!" in msg_history.content:
                        found_existing_verify_msg = True
                        print("✅ 기존 인증 메시지 발견. 뷰 재등록 시도.")
                        try:
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

        # 파티 모집 스레드의 뷰도 재등록 (봇 재시작 시 필요)
        for thread_id_str, info in list(state["party_infos"].items()):
            if info.get("embed_msg_id"):
                thread_channel = guild.get_channel(int(thread_id_str))
                if thread_channel:
                    try:
                        # 파티 뷰는 스레드 생성 시 보내지므로, 재시작 시 별도 재등록 로직은 불필요하지만,
                        # 혹시 모를 상황에 대비하여 View 객체 자체는 add_view로 등록해두는 것이 안전
                        print(f"PartyView for thread {thread_id_str} registered.")
                    except Exception as e:
                        print(f"파티 스레드 뷰 재등록 중 오류 발생: {e}")

    # 리마인더 루프 시작
    reminder_loop.start() # @tasks.loop를 사용하므로 .start() 호출

# === 시작 ===
load_state()
bot.run(TOKEN)