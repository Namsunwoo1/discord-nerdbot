import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Select
import pytz # pytz 라이브러리 임포트 확인

# === .env 로드 ===
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("❌ DISCORD_TOKEN을 .env 파일에서 불러오지 못했습니다!")
    exit(1)
else:
    print("✅ DISCORD_TOKEN 정상 로드됨")

# === 설정 ===
# TODO: 아래 ID들을 실제 디스코드 서버 및 채널, 역할 ID로 변경해주세요!
YOUR_GUILD_ID = 1388092210519605361 
ROLE_SELECT_CHANNEL_ID = 1388211020576587786
VERIFY_CHANNEL_ID = 1391373955507552296
VERIFIED_ROLE_ID = 1390356825454416094
GUEST_ROLE_ID = 1393038834106892379
VERIFY_LOG_CHANNEL_ID = 1391756822763012190
WELCOME_CHANNEL_ID = 1390643886656847986 # 이전과 다를 수 있으니 다시 확인해주세요!

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

# 상태 저장을 위한 파일명
DATA_FILE = "state.json" 

# 봇의 현재 상태를 저장할 딕셔너리 (전역 변수)
# role_message_id: 역할 선택 메시지의 ID (필요시 사용)
# party_infos: { 스레드ID: {파티정보딕셔너리} }
# initial_message_id: 역할 선택을 시작하는 채널의 초기 메시지 ID (지속성용)
state = {"role_message_id": None, "party_infos": {}, "initial_message_id": None}

# KST 시간대 정의 (UTC+9)
KST = pytz.timezone('Asia/Seoul')

# === 상태 로드 및 저장 함수 ===
def save_state():
    """현재 봇의 상태를 JSON 파일로 저장합니다."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        # datetime 객체를 타임스탬프로 변환하여 저장
        serializable_state = state.copy()
        party_infos_copy = {}
        for thread_id, info in serializable_state.get('party_infos', {}).items():
            info_copy = info.copy()
            if 'reminder_time' in info_copy and isinstance(info_copy['reminder_time'], datetime):
                info_copy['reminder_time'] = info_copy['reminder_time'].timestamp()
            if 'party_time' in info_copy and isinstance(info_copy['party_time'], datetime):
                info_copy['party_time'] = info_copy['party_time'].timestamp()
            party_infos_copy[thread_id] = info_copy
        serializable_state['party_infos'] = party_infos_copy
        json.dump(serializable_state, f, ensure_ascii=False, indent=4)

def load_state():
    """JSON 파일에서 봇의 상태를 불러옵니다."""
    global state
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                loaded = json.load(f)
                
                # 'party_infos'의 datetime 객체 변환 처리
                if 'party_infos' in loaded:
                    for thread_id, info in loaded['party_infos'].items():
                        if 'reminder_time' in info and info['reminder_time'] is not None:
                            # 타임스탬프를 UTC datetime 객체로 변환
                            info['reminder_time'] = datetime.fromtimestamp(info['reminder_time'], tz=timezone.utc)
                        if 'party_time' in info and info['party_time'] is not None:
                            # 타임스탬프를 UTC datetime 객체로 변환
                            info['party_time'] = datetime.fromtimestamp(info['party_time'], tz=timezone.utc)
                
                state = {
                    "role_message_id": loaded.get("role_message_id"),
                    "party_infos": loaded.get("party_infos", {}),
                    "initial_message_id": loaded.get("initial_message_id")
                }
                print("✅ 상태 파일 로드 완료")
            except json.JSONDecodeError:
                print("❌ state.json 파일이 손상되었거나 비어 있습니다. 초기화합니다.")
                state = {"role_message_id": None, "party_infos": {}, "initial_message_id": None}
            except Exception as e:
                print(f"❌ state 로드 중 알 수 없는 오류 발생: {e}. 상태를 초기화합니다.")
                state = {"role_message_id": None, "party_infos": {}, "initial_message_id": None}
    else:
        print("ℹ️ state.json 파일이 없습니다. 새로운 상태를 생성합니다.")

# === 인텐트 및 봇 초기화 ===
# 모든 인텐트를 사용하는 경우 discord.Intents.all()
# 특정 인텐트만 필요한 경우 discord.Intents.default() 후 필요한 인텐트 활성화
intents = discord.Intents.default()
intents.message_content = True # 봇이 메시지 내용을 읽을 수 있도록 허용
intents.members = True # 길드 멤버 정보 (닉네임, 역할 등)를 가져올 수 있도록 허용
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# === 역할 선택 UI ===

class RoleSelectButton(Button):
    """카테고리별 역할을 선택하거나 해제하는 버튼."""
    def __init__(self, role_name, emoji, role_type):
        super().__init__(
            label=role_name,
            style=discord.ButtonStyle.secondary,
            emoji=emoji,
            custom_id=f"{role_type}_{role_name}_button"
        )
        self.role_name = role_name
        self.role_type = role_type

    async def callback(self, interaction: discord.Interaction):
        role_id = ROLE_IDS[self.role_type].get(self.role_name)
        if not role_id:
            return await interaction.response.send_message(f"'{self.role_name}' 역할 ID를 찾을 수 없습니다.", ephemeral=True)

        role = interaction.guild.get_role(role_id)
        if not role:
            return await interaction.response.send_message(f"'{self.role_name}' 역할을 서버에서 찾을 수 없습니다.", ephemeral=True)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"'{self.role_name}' 역할이 제거되었습니다.", ephemeral=True)
        else:
            # MBTI 역할은 한 번에 하나만 가질 수 있도록 처리
            if self.role_type == "MBTI":
                for existing_role in interaction.user.roles:
                    if existing_role.name in MBTI_ROLE_NAMES:
                        await interaction.user.remove_roles(existing_role)
                        break
            
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"'{self.role_name}' 역할이 추가되었습니다.", ephemeral=True)


class CategorySelectView(View):
    """아르카나/MBTI 카테고리를 선택하는 초기 뷰."""
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
    """선택된 카테고리(아르카나 또는 MBTI)에 해당하는 역할 버튼들을 보여주는 뷰."""
    def __init__(self, role_category: str):
        super().__init__(timeout=None)
        self.role_category = role_category
        
        roles_to_display = ROLE_IDS[self.role_category]

        for role_name in roles_to_display.keys():
            self.add_item(RoleSelectButton(role_name, EMOJI_MAP.get(role_name, "❓"), self.role_category))
        
        self.add_item(BackToCategoryButton())

class BackToCategoryButton(Button):
    """카테고리 선택 뷰로 돌아가는 버튼."""
    def __init__(self):
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

# === 파티 모집 기능 ===

class PartyRoleSelect(Select):
    """파티 참여자가 자신의 아르카나를 선택하고 참여하는 드롭다운 메뉴."""
    def __init__(self):
        options = [
            discord.SelectOption(label=role, emoji=EMOJI_MAP.get(role, "❓"))
            for role in ROLE_IDS["JOB"].keys() # JOB 역할만 선택 가능
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
    """파티 모집자가 파티 정보를 수정할 수 있는 버튼."""
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

            # 파티 시간 파싱 및 UTC 변환 로직 (KST 기준)
            current_year = datetime.now(KST).year
            party_time_utc = None
            try:
                # 사용자가 입력한 날짜와 시간을 KST 기준으로 파싱
                parsed_dt_kst = KST.localize(datetime.strptime(f"{current_year}-{date_str} {time_str}", "%Y-%m/%d %H:%M"))
                
                # 만약 파싱된 시간이 현재 시간보다 과거라면 (지난 날짜라면), 다음 해로 자동 조정
                if parsed_dt_kst < datetime.now(KST):
                    parsed_dt_kst = KST.localize(datetime.strptime(f"{current_year + 1}-{date_str} {time_str}", "%Y-%m/%d %H:%M"))
                    
                party_time_utc = parsed_dt_kst.astimezone(timezone.utc)
                
            except ValueError:
                raise ValueError("날짜/시간 형식이 올바르지 않거나 유효하지 않은 날짜입니다. (예: 7/10 20:30)")
            
            if not party_time_utc:
                raise ValueError("파티 시간 설정에 실패했습니다. 형식과 날짜를 다시 확인해주세요.")


            # 알림 시간 (파티 시작 10분 전)
            reminder_time_utc = party_time_utc - timedelta(minutes=10)

            info.update({
                "dungeon": dungeon, 
                "date": date_str, 
                "time": time_str, 
                "reminder_time": reminder_time_utc, # datetime 객체로 저장
                "party_time": party_time_utc, # datetime 객체로 저장
            })
            save_state()
            await update_party_embed(thread_id)
            await interaction.followup.send("✅ 파티 정보가 성공적으로 수정되었습니다!", ephemeral=True)

            # 수정된 파티 시간으로 스레드 삭제 재예약
            bot.loop.create_task(schedule_thread_deletion(thread_id, party_time_utc))

        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ 시간 초과로 수정이 취소되었습니다.", ephemeral=True)
        except ValueError as e:
            await interaction.followup.send(f"⚠️ {e}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ 오류 발생: {e}", ephemeral=True)

class PartyView(View):
    """파티 모집 임베드에 포함될 뷰 (역할 선택 및 수정 버튼)."""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PartyRoleSelect())
        self.add_item(PartyEditButton())

async def update_party_embed(thread_id: int):
    """주어진 스레드 ID의 파티 모집 임베드 메시지를 업데이트합니다."""
    info = state["party_infos"].get(str(thread_id))
    if not info:
        print(f"DEBUG: update_party_embed - 파티 정보 없음 for thread_id {thread_id}")
        return

    thread = bot.get_channel(thread_id)
    if not thread or not isinstance(thread, discord.Thread):
        print(f"DEBUG: update_party_embed - 스레드 채널을 찾을 수 없거나 스레드가 아님 for {thread_id}")
        # 스레드가 사라진 경우, state에서도 제거
        if str(thread_id) in state["party_infos"]:
            del state["party_infos"][str(thread_id)]
            save_state()
        return

    try:
        embed_msg = await thread.fetch_message(info["embed_msg_id"])
    except discord.NotFound:
        print(f"DEBUG: update_party_embed - 임베드 메시지 ({info['embed_msg_id']})를 찾을 수 없음. 스레드 {thread_id}")
        return
    except Exception as e:
        print(f"DEBUG: update_party_embed - 임베드 메시지 가져오기 실패: {e} for thread {thread_id}")
        return

    participants_str = "아직 없음"
    if info["participants"]:
        participants_list = []
        for user_id_str, role_name in info["participants"].items():
            user = thread.guild.get_member(int(user_id_str))
            if user:
                participants_list.append(f"• {user.display_name} ({role_name})")
            else:
                participants_list.append(f"• (알 수 없음) ({role_name})")
        participants_str = "\n".join(participants_list)

    new_embed = discord.Embed(
        title=f"🎯 파티 모집중! - {info['dungeon']}",
        description=(
            f"📍 던전: **{info['dungeon']}**\n"
            f"📅 날짜: **{info['date']}**\n"
            f"⏰ 시간: **{info['time']}**\n\n"
            f"**🧑‍🤝‍🧑 현재 참여자: {len(info['participants'])}명**\n{participants_str}\n\n"
            "---"
        ),
        color=0x00ff00
    )
    owner_member = thread.guild.get_member(info['owner_id'])
    if owner_member:
        new_embed.set_footer(text=f"모집자: {owner_member.display_name}", icon_url=owner_member.avatar.url if owner_member.avatar else discord.Embed.Empty)

    try:
        await embed_msg.edit(embed=new_embed)
        print(f"DEBUG: 스레드 {thread_id} 임베드 업데이트 완료.")
    except Exception as e:
        print(f"DEBUG: 스레드 {thread_id} 임베드 업데이트 실패: {e}")

async def schedule_thread_deletion(thread_id: int, delete_time_utc: datetime):
    """지정된 시간에 스레드를 삭제하도록 예약합니다."""
    
    now_utc = datetime.now(timezone.utc)
    time_to_wait = (delete_time_utc - now_utc).total_seconds()

    if time_to_wait <= 0:
        print(f"⚠️ 스레드 {thread_id} 삭제 시간이 현재 시간보다 빠르거나 같습니다. 즉시 삭제를 시도합니다.")
        # 만약 삭제 시간이 이미 지났다면 바로 삭제 시도
        try:
            thread_channel = bot.get_channel(thread_id)
            if thread_channel and isinstance(thread_channel, discord.Thread):
                await thread_channel.delete()
                print(f"✅ 스레드 {thread_id}가 즉시 삭제되었습니다.")
                if str(thread_id) in state["party_infos"]:
                    del state["party_infos"][str(thread_id)]
                    save_state()
            else:
                print(f"⚠️ 스레드 {thread_id}를 찾을 수 없거나 스레드 객체가 아닙니다. (이미 삭제되었을 수 있음)")
                # 스레드가 이미 삭제된 경우 state에서도 제거
                if str(thread_id) in state["party_infos"]:
                    del state["party_infos"][str(thread_id)]
                    save_state()
        except discord.NotFound:
            print(f"⚠️ 스레드 {thread_id}를 찾을 수 없어 삭제할 수 없습니다. (이미 삭제되었을 수 있음)")
            if str(thread_id) in state["party_infos"]:
                del state["party_infos"][str(thread_id)]
                save_state()
        except Exception as e:
            print(f"❌ 스레드 {thread_id} 즉시 삭제 중 오류 발생: {e}")
        return

    print(f"⏳ 스레드 {thread_id}는 {time_to_wait:.0f}초 후 (UTC: {delete_time_utc.isoformat()}) 삭제될 예정입니다.")
    
    await asyncio.sleep(time_to_wait)

    try:
        thread_channel = bot.get_channel(thread_id)
        if thread_channel and isinstance(thread_channel, discord.Thread):
            await thread_channel.delete()
            print(f"✅ 스레드 {thread_id}가 모집 시간 종료로 인해 삭제되었습니다.")
            if str(thread_id) in state["party_infos"]:
                del state["party_infos"][str(thread_id)]
                save_state()
        else:
            print(f"⚠️ 스레드 {thread_id}를 찾을 수 없거나 이미 삭제되었습니다.")
            if str(thread_id) in state["party_infos"]:
                del state["party_infos"][str(thread_id)]
                save_state()
    except discord.NotFound:
        print(f"⚠️ 스레드 {thread_id}를 찾을 수 없어 삭제할 수 없습니다. (이미 삭제되었을 수 있음)")
        if str(thread_id) in state["party_infos"]:
            del state["party_infos"][str(thread_id)]
            save_state()
    except Exception as e:
        print(f"❌ 스레드 {thread_id} 삭제 중 오류 발생: {e}")

# === 명령어: 파티 모집 ===
@bot.command()
async def 모집(ctx):
    # 1. !모집 명령어 메시지 자동 삭제
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        print(f"❌ '{ctx.guild.name}' 길드에서 메시지 삭제 권한이 없습니다.")
    except Exception as e:
        print(f"⚠️ 메시지 삭제 중 오류 발생: {e}")

    if not ctx.guild:
        await ctx.send("이 명령어는 서버 채널에서만 사용할 수 있습니다.")
        return

    # '찡긋' 역할 확인
    verified_role = ctx.guild.get_role(VERIFIED_ROLE_ID)
    if not verified_role or verified_role not in ctx.author.roles:
        await ctx.send("⛔ 파티 모집은 `찡긋` 역할을 가진 멤버만 가능합니다. 먼저 인증을 완료해주세요!", delete_after=10) # 10초 후 자동 삭제
        return

    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    
    # 봇의 질문 메시지 (delete_after 추가)
    bot_question_msg = await ctx.send("📥 파티 정보를 한 줄로 입력해주세요. 예: `브리레흐1-3관 7/6 20:00`", delete_after=15)
    
    try:
        msg = await bot.wait_for("message", timeout=30.0, check=check)
        
        # --- 사용자 메시지 및 봇 질문 메시지 삭제 ---
        try:
            # 사용자가 입력한 파티 정보 메시지 삭제
            await msg.delete()
            # 봇의 질문 메시지도 삭제 (만약 아직 남아있다면)
            await bot_question_msg.delete() 
        except discord.Forbidden:
            print(f"❌ '{ctx.guild.name}' 길드에서 사용자 메시지 또는 봇 질문 메시지 삭제 권한이 없습니다.")
        except Exception as e:
            print(f"⚠️ 사용자 메시지/봇 질문 메시지 삭제 중 오류 발생: {e}")
        # --- 삭제 끝 ---

        content_parts = msg.content.strip().split()
        if len(content_parts) < 3:
            await ctx.send("⚠️ 입력 형식이 올바르지 않습니다. (예: `던전명 7/6 20:00`)", delete_after=10) # 10초 후 자동 삭제
            return

        dungeon = content_parts[0]
        date_str = content_parts[1]
        time_str = content_parts[2]

        current_year = datetime.now(KST).year # KST 기준 현재 연도
        party_time_utc = None
        try:
            # 사용자가 입력한 날짜와 시간을 KST 기준으로 파싱
            parsed_dt_kst = KST.localize(datetime.strptime(f"{current_year}-{date_str} {time_str}", "%Y-%m/%d %H:%M"))
            
            # 만약 파싱된 시간이 현재 시간보다 과거라면 (지난 날짜라면), 다음 해로 자동 조정
            if parsed_dt_kst < datetime.now(KST):
                parsed_dt_kst = KST.localize(datetime.strptime(f"{current_year + 1}-{date_str} {time_str}", "%Y-%m/%d %H:%M"))
                
            party_time_utc = parsed_dt_kst.astimezone(timezone.utc)
            
        except ValueError:
            raise ValueError("날짜/시간 형식이 올바르지 않거나 유효하지 않은 날짜입니다. (예: 7/6 20:00)")
        
        if not party_time_utc:
            raise ValueError("파티 시간 설정에 실패했습니다. 형식과 날짜를 다시 확인해주세요.")

        reminder_time_utc = party_time_utc - timedelta(minutes=10) # 10분 전 알림

    except asyncio.TimeoutError:
        # 시간 초과 시 봇의 질문 메시지도 삭제
        try:
            await bot_question_msg.delete()
        except Exception:
            pass # 이미 삭제되었거나 다른 오류 발생 시 무시
        await ctx.send("⏰ 시간 초과로 파티 생성이 취소되었습니다.", delete_after=10) # 10초 후 자동 삭제
        return
    except ValueError as e:
        # 오류 메시지 전송 후 봇의 질문 메시지 삭제
        try:
            await bot_question_msg.delete()
        except Exception:
            pass
        await ctx.send(f"⚠️ {e}", delete_after=10) # 10초 후 자동 삭제
        return
    except Exception as e:
        # 오류 메시지 전송 후 봇의 질문 메시지 삭제
        try:
            await bot_question_msg.delete()
        except Exception:
            pass
        await ctx.send(f"⚠️ 파티 정보 입력 중 오류 발생: {e}", delete_after=10) # 10초 후 자동 삭제
        return

    # 스레드 이름 변경: [던전명] 날짜 시간 - 모집자닉네임님의 파티 모집
    # 스레드 생성 시도 (권한 부족에 대한 예외 처리 추가)
    thread = None
    try:
        thread = await ctx.channel.create_thread(
            name=f"[{dungeon}] {date_str} {time_str} - {ctx.author.display_name}님의 파티 모집",
            type=discord.ChannelType.public_thread,
            auto_archive_duration=60, # 기본 60분 (1시간) 자동 보관 설정
        )
        print(f"DEBUG: 스레드 '{thread.name}' (ID: {thread.id}) 생성 성공.")
    except discord.Forbidden:
        await ctx.send("❌ 스레드를 생성할 권한이 없습니다. 봇의 권한을 확인해주세요.", delete_after=15)
        print(f"ERROR: 길드 '{ctx.guild.name}'에서 스레드 생성 권한 부족.")
        return # 권한이 없으므로 여기서 함수 종료
    except Exception as e:
        await ctx.send(f"❌ 스레드 생성 중 오류 발생: {e}", delete_after=15)
        print(f"ERROR: 스레드 생성 중 예상치 못한 오류 발생: {e}")
        return # 오류 발생 시 함수 종료

    # 파티 정보 딕셔너리 생성 및 저장
    party_info = {
        "dungeon": dungeon,
        "date": date_str,
        "time": time_str,
        "reminder_time": reminder_time_utc, # datetime 객체로 저장
        "party_time": party_time_utc, # datetime 객체로 저장
        "participants": {}, # {user_id: role_name}
        "embed_msg_id": None,
        "owner_id": ctx.author.id,
    }

    state["party_infos"][str(thread.id)] = party_info
    save_state()

    # 초기 임베드 메시지 생성 및 전송
    initial_embed = discord.Embed(
        title=f"🎯 파티 모집중! - {dungeon}",
        description=(
            f"📍 던전: **{dungeon}**\n"
            f"📅 날짜: **{date_str}**\n"
            f"⏰ 시간: **{time_str}**\n\n"
            f"**🧑‍🤝‍🧑 현재 참여자: 0명**\n(아직 없음)\n\n"
            "---"
        ),
        color=0x00ff00
    )
    owner_member = ctx.guild.get_member(party_info['owner_id'])
    if owner_member:
        initial_embed.set_footer(text=f"모집자: {owner_member.display_name}", icon_url=owner_member.avatar.url if owner_member.avatar else discord.Embed.Empty)

    embed_msg = await thread.send(embed=initial_embed)
    await embed_msg.pin() # 메시지 고정
    party_info["embed_msg_id"] = embed_msg.id
    save_state() # 임베드 메시지 ID 저장 후 다시 상태 저장

    await thread.send(view=PartyView()) # 파티 참여/수정 버튼 뷰 전송
    await ctx.send(f"{ctx.author.mention}님, 파티 모집 스레드가 생성되었습니다: {thread.mention}", delete_after=10) # 10초 후 자동 삭제

    # 모집 시간 종료 후 스레드 자동 삭제 스케줄링
    bot.loop.create_task(schedule_thread_deletion(thread.id, party_time_utc))


## MBTI 통계 및 확인 기능


@bot.command()
async def mbti통계(ctx):
    """서버 내 MBTI 역할 통계를 보여줍니다."""
    guild = ctx.guild
    if not guild:
        await ctx.send("이 명령어는 서버에서만 사용할 수 있습니다.")
        return

    mbti_roles_dict = {name: guild.get_role(ROLE_IDS["MBTI"][name]) for name in MBTI_ROLE_NAMES if name in ROLE_IDS["MBTI"]}
    mbti_roles_dict = {name: role for name, role in mbti_roles_dict.items() if role} # 실제 서버에 존재하는 역할만 포함

    if not mbti_roles_dict:
        await ctx.send("서버에 설정된 MBTI 역할이 없습니다. `ROLE_IDS['MBTI']` 또는 `MBTI_ROLE_NAMES`를 확인해주세요.")
        return

    mbti_counts = {name: 0 for name in MBTI_ROLE_NAMES} # 모든 MBTI 역할을 0으로 초기화
    
    # 서버의 모든 멤버를 가져와서 MBTI 역할 카운트
    members = []
    async for member in guild.fetch_members(limit=None): # 모든 멤버를 가져오기 (시간이 걸릴 수 있음)
        members.append(member)

    for member in members:
        for role in member.roles:
            if role.name in mbti_counts:
                mbti_counts[role.name] += 1
    
    # 카운트가 높은 순서대로 정렬
    sorted_mbti_counts = sorted(mbti_counts.items(), key=lambda item: item[1], reverse=True)

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
    mbti_type = mbti_type.upper() # 대소문자 구분 없이 처리

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
    async for member in ctx.guild.fetch_members(limit=None): # 모든 멤버를 가져오기
        if mbti_role in member.roles:
            members_with_role.append(member.display_name)
    
    embed = discord.Embed(
        title=f"👥 {mbti_type} 유형 멤버 목록",
        color=0x7289DA
    )

    if members_with_role:
        description_text = "\n".join(members_with_role)
        if len(description_text) > 1900: # Discord 임베드 설명 최대 길이 (2048자) 고려
            description_text = description_text[:1900] + "\n...(이하 생략)"
        embed.description = description_text
        embed.set_footer(text=f"총 {len(members_with_role)}명")
    else:
        embed.description = f"현재 '{mbti_type}' 역할을 가진 멤버가 없습니다."

    await ctx.send(embed=embed)


## 봇 도움말 기능


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
        value=f"역할 선택은 <#{ROLE_SELECT_CHANNEL_ID}> 채널에서, 인증은 <#{VERIFY_CHANNEL_ID}> 채널에서 버튼을 통해 진행할 수 있습니다.",
        inline=False
    )

    embed.set_footer(text=f"문의사항은 서버 관리자에게 문의해주세요. | 봇 버전: v0.1")
    embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else discord.Embed.Empty)

    await ctx.send(embed=embed)


## 배경 작업 (리마인더, 스레드 자동 보관)


@tasks.loop(minutes=1)
async def reminder_loop():
    """매 1분마다 파티 리마인더 알림을 확인하고 스레드를 자동 보관합니다."""
    await bot.wait_until_ready() # 봇이 완전히 준비될 때까지 기다림
    now_utc = datetime.now(timezone.utc)
    print(f"DEBUG: Reminder loop started at {now_utc.isoformat()}")
    
    print(f"DEBUG: Current party_infos in state: {list(state['party_infos'].keys())}")

    for thread_id_str, info in list(state["party_infos"].items()):
        thread_id = int(thread_id_str)
        print(f"DEBUG: Processing party for thread ID: {thread_id_str}")
        
        thread = bot.get_channel(thread_id)
        
        # 스레드가 유효한지 먼저 확인
        if not thread or not isinstance(thread, discord.Thread):
            print(f"DEBUG: 스레드 {thread_id}를 찾을 수 없거나 스레드 객체가 아닙니다. (type: {type(thread)}) 파티 정보에서 제거합니다.")
            if str(thread_id) in state["party_infos"]:
                del state["party_infos"][str(thread_id)]
                save_state()
            continue # 다음 파티 정보로 넘어감

        # --- 스레드 자동 보관 로직 ---
        party_time_utc = info.get("party_time") 

        if party_time_utc: # party_time이 있을 때만 보관 로직 실행
            # 파티 시작 시간이 1시간 지났고, 아직 스레드가 활성화 상태라면 보관
            if not thread.archived and party_time_utc + timedelta(hours=1) < now_utc:
                try:
                    await thread.edit(archived=True, reason="파티 모집 시간 1시간 경과, 스레드 자동 보관")
                    print(f"✅ 스레드 '{thread.name}' (ID: {thread_id_str}) 자동 보관 처리됨.")
                except discord.Forbidden:
                    print(f"❌ 스레드 '{thread.name}' (ID: {thread_id_str}) 보관 권한이 없습니다. 봇 권한을 확인해주세요.")
                except Exception as e:
                    print(f"❌ 스레드 '{thread.name}' (ID: {thread_id_str}) 보관 중 오류 발생: {e}")
        # --- 스레드 자동 보관 로직 끝 ---

        # --- 리마인더 알림 로직 ---
        reminder_dt_utc = info.get("reminder_time") 
        
        if reminder_dt_utc is None: # 이미 알림을 보냈거나 설정되지 않은 경우
            continue

        print(f"DEBUG: 스레드 {thread_id_str} - Reminder: {reminder_dt_utc.isoformat()}, Now: {now_utc.isoformat()}")
        
        time_until_reminder = reminder_dt_utc - now_utc
        print(f"DEBUG: 스레드 {thread_id_str} - Time until reminder: {time_until_reminder}")
        
        # 리마인더 시간이 현재 시간과 1분 이내로 남았을 경우 또는 이미 지났지만 봇 재시작 등으로 알림을 못 보냈을 경우
        if timedelta(minutes=0) <= time_until_reminder < timedelta(minutes=1) or (reminder_dt_utc < now_utc and time_until_reminder > timedelta(minutes=-1)): # 과거 1분 이내의 시간도 포함
            guild = bot.get_guild(YOUR_GUILD_ID)
            if not guild:
                print(f"경고: 길드 ID {YOUR_GUILD_ID}를 찾을 수 없습니다. (리마인더 루프)")
                info["reminder_time"] = None # 길드를 찾을 수 없으면 알림 보낼 수 없으므로 초기화
                save_state()
                continue

            mentions = []
            for user_id_str in info.get("participants", {}).keys():
                member = guild.get_member(int(user_id_str))
                if member:
                    mentions.append(member.mention)
            
            # 스레드가 존재하고 유효한 경우에만 알림 발송 시도
            if thread and isinstance(thread, discord.Thread):
                try:
                    await thread.send(
                        f"⏰ **리마인더 알림!**\n{' '.join(mentions)}\n"
                        f"`{info['dungeon']}` 던전이 10분 후에 시작됩니다! **({info['date']} {info['time']})**"
                    )
                    info["reminder_time"] = None # 알림 보낸 후 reminder_time 초기화
                    save_state()
                    print(f"✅ 리마인더 전송 완료: 스레드 {thread_id_str} - {info['dungeon']}")
                except discord.Forbidden:
                    print(f"❌ 리마인더 전송 실패: 스레드 {thread_id_str}에 메시지 보낼 권한이 없습니다.")
                    info["reminder_time"] = None # 권한 없으면 더 이상 시도 무의미
                    save_state()
                except Exception as e:
                    print(f"❌ 리마인더 전송 실패 (스레드 {thread_id_str}): {e}")
                    # 오류 발생 시 reminder_time을 초기화하지 않아서 다음 루프에서 재시도할 수 있도록 함
                    # 그러나 너무 많은 오류가 발생하면 루프가 느려질 수 있으므로, 재시도 로직을 더 견고하게 할 필요는 있음
            else:
                print(f"경고: 스레드 ID {thread_id_str}를 찾을 수 없거나 이미 삭제되었습니다. 리마인더 알림을 보낼 수 없습니다.")
                info["reminder_time"] = None # 스레드가 없으면 알림 보낼 수 없으므로 초기화
                save_state()
        
        # 리마인더 시간이 너무 많이 지난 경우 (예: 봇이 오래 꺼져있었을 때) 초기화
        elif reminder_dt_utc < now_utc - timedelta(minutes=5) and reminder_dt_utc is not None: # 5분 이상 지났으면 초기화
            print(f"DEBUG: 스레드 {thread_id_str} - 리마인더 시간이 너무 오래 지났습니다. 초기화.")
            info["reminder_time"] = None
            save_state()


## 새 멤버 환영 및 인증 안내


@bot.event
async def on_member_join(member):
    """새 멤버가 서버에 들어올 때 '손님' 역할을 부여하고 환영 메시지를 보냅니다."""
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


## 봇 실행 시 초기화 로직


@bot.event
async def on_ready():
    """봇이 로그인되어 준비되면 실행되는 초기화 작업들."""
    print(f"✅ 봇 로그인 완료: {bot.user}")
    guild = bot.get_guild(YOUR_GUILD_ID)

    if guild:
        try:
            await guild.me.edit(nick="찡긋봇") # 봇 닉네임 변경 시도
        except Exception as e:
            print(f"닉네임 변경 실패: {e}")

        # 봇 재시작 시 Persistent View 등록 (커스텀 ID를 가진 View)
        bot.add_view(CategorySelectView())
        bot.add_view(VerifyView())
        bot.add_view(PartyView()) 

        # 역할 선택 메시지 확인 및 재전송 (CategorySelectView)
        role_channel = guild.get_channel(ROLE_SELECT_CHANNEL_ID)
        if role_channel:
            if state["initial_message_id"]: # 저장된 메시지 ID가 있다면 재사용 시도
                try:
                    initial_msg = await role_channel.fetch_message(state["initial_message_id"])
                    await initial_msg.edit(view=CategorySelectView())
                    print(f"✅ 기존 역할 선택 초기 메시지 ({state['initial_message_id']})에 뷰 재등록 완료.")
                except discord.NotFound: # 메시지가 삭제되었다면 새로 전송
                    print(f"⚠️ 저장된 역할 선택 초기 메시지 ({state['initial_message_id']})를 찾을 수 없습니다. 새로 전송합니다.")
                    state["initial_message_id"] = None
                    save_state()
                except Exception as e:
                    print(f"역할 선택 초기 메시지 확인 중 오류 발생: {e}")
                    state["initial_message_id"] = None
                    save_state()

            if not state["initial_message_id"]: # 메시지가 없거나 새로고침이 필요하면 전송
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

        # 인증 메시지 확인 및 재전송 (VerifyView)
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
                
                if not found_existing_verify_msg: # 기존 메시지가 없으면 새로 전송
                    await verify_channel.send(
                        "✅ 서버에 오신 걸 환영합니다!\n아래 버튼을 눌러 인증을 완료해주세요.",
                        view=VerifyView()
                    )
                    print("✅ 새로운 인증 메시지 전송 완료.")
            except Exception as e:
                print(f"인증 메시지 전송 오류: {e}")

        # 봇 재시작 시 기존 파티 모집 스레드의 임베드 업데이트 및 삭제 스케줄링 재개
        # `state["party_infos"]`는 load_state()에서 이미 로드됨
        for thread_id_str, info in list(state["party_infos"].items()):
            thread_id = int(thread_id_str)
            # 각 스레드의 embed_msg_id가 있는 경우 update_party_embed를 한번 호출하여 최신화
            if info.get("embed_msg_id"):
                await update_party_embed(thread_id)
                print(f"✅ 스레드 {thread_id} 임베드 정보 최신화 완료.")

            # 파티 시간이 유효하면 삭제 스케줄링 재개
            party_time = info.get("party_time")
            if party_time and isinstance(party_time, datetime) and party_time > datetime.now(timezone.utc):
                bot.loop.create_task(schedule_thread_deletion(thread_id, party_time))
                print(f"✅ 스레드 {thread_id} 삭제 스케줄링 재개 완료.")
            else:
                print(f"⚠️ 스레드 {thread_id}의 파티 시간 정보가 유효하지 않거나 이미 지났습니다. 스케줄링 건너뜀.")
                # 이미 지난 파티는 state에서 제거하거나 (삭제 스케줄링이 처리했어야 함)
                # 만약 스레드가 남아있다면 즉시 삭제 시도
                bot.loop.create_task(schedule_thread_deletion(thread_id, datetime.now(timezone.utc)))


    # 리마인더 루프 시작
    reminder_loop.start()

# === 봇 실행 ===
load_state() # 봇 실행 전 상태 로드
bot.run(TOKEN) # 봇 실행