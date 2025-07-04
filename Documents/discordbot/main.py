import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import asyncio
from datetime import datetime, timedelta

# .env 경로 명시적 지정 및 로드
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

# 토큰 가져오기 및 유효성 검사
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

ROLE_SELECT_CHANNEL_ID = 1388211020576587786
PARTY_RECRUIT_CHANNEL_ID = 1388112858365300836
WELCOME_CHANNEL_NAME = "🌊｜반갑죠"

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

party_info = {
    "dungeon": None,
    "date": None,
    "time": None,
    "thread": None,
    "embed_msg": None,
    "participants": {},  # {discord.Member: 직업명}
    "reminder_time": None,
}

class RoleToggleButton(Button):
    def __init__(self, role_name, emoji):
        super().__init__(label=role_name, style=discord.ButtonStyle.secondary, emoji=emoji)
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction):
        try:
            guild = interaction.guild
            role = guild.get_role(ROLE_IDS[self.role_name])
            if role is None:
                await interaction.response.send_message("⚠️ 역할을 찾을 수 없습니다.", ephemeral=True)
                return
            member = interaction.user
            if role in member.roles:
                await member.remove_roles(role)
                await interaction.response.send_message(f"'{self.role_name}' 역할이 제거되었습니다.", ephemeral=True)
            else:
                await member.add_roles(role)
                await interaction.response.send_message(f"'{self.role_name}' 역할이 추가되었습니다.", ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message("오류가 발생했습니다.", ephemeral=True)
            print(f"Error in RoleToggleButton.callback: {e}")

class RoleSelectView(View):
    def __init__(self):
        super().__init__(timeout=None)
        for role_name, emoji in [
            ("세이크리드 가드", "🛡️"),
            ("다크 메이지", "🔮"),
            ("세인트 바드", "🎵"),
            ("블래스트 랜서", "⚔️"),
            ("엘레멘탈 나이트", "🗡️"),
            ("알케믹 스팅어", "🧪"),
            ("포비든 알케미스트", "☠️"),
            ("배리어블 거너", "🔫"),
        ]:
            self.add_item(RoleToggleButton(role_name, emoji))

class PartyRoleSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="세이크리드 가드", emoji="🛡️"),
            discord.SelectOption(label="다크 메이지", emoji="🔮"),
            discord.SelectOption(label="세인트 바드", emoji="🎵"),
            discord.SelectOption(label="블래스트 랜서", emoji="⚔️"),
            discord.SelectOption(label="엘레멘탈 나이트", emoji="🗡️"),
            discord.SelectOption(label="알케믹 스팅어", emoji="🧪"),
            discord.SelectOption(label="포비든 알케미스트", emoji="☠️"),
            discord.SelectOption(label="배리어블 거너", emoji="🔫"),
            discord.SelectOption(label="참여 취소", emoji="❌"),
        ]
        super().__init__(placeholder="직업을 선택하세요! 참여 취소도 가능합니다.", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            user = interaction.user
            selected = self.values[0]

            if selected == "참여 취소":
                if user in party_info["participants"]:
                    del party_info["participants"][user]
                    await interaction.response.send_message("파티 참여가 취소되었습니다.", ephemeral=True)
                else:
                    await interaction.response.send_message("아직 파티에 참여하지 않았습니다.", ephemeral=True)
            else:
                # 8명 초과해도 예비 인원으로 등록 가능
                party_info["participants"][user] = selected
                await interaction.response.send_message(f"'{selected}' 역할로 파티에 참여했습니다!", ephemeral=True)

            desc_lines = [
                f"📍 던전: **{party_info['dungeon']}**",
                f"📅 날짜: **{party_info['date']}**",
                f"⏰ 시간: **{party_info['time']}**",
                "",
                "**🧑‍🤝‍🧑 현재 참여자 명단:**",
            ]

            main_participants = list(party_info["participants"].items())[:8]
            reserve_participants = list(party_info["participants"].items())[8:]

            if main_participants:
                for member, role in main_participants:
                    desc_lines.append(f"- {member.display_name}: {role}")
            else:
                desc_lines.append("(아직 없음)")

            if reserve_participants:
                desc_lines.append("\n**📄 예비 인원:**")
                for member, role in reserve_participants:
                    desc_lines.append(f"- {member.display_name}: {role}")

            desc_lines.append("\n👇 셀렉트 메뉴에서 역할을 선택하거나 참여 취소를 할 수 있습니다! 최대 8명 + 예비 인원 허용.")

            new_description = "\n".join(desc_lines)
            new_embed = discord.Embed(title="🎯 파티 모집중!", description=new_description, color=0x00ff00)

            if party_info["embed_msg"]:
                await party_info["embed_msg"].edit(embed=new_embed)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message("오류가 발생했습니다.", ephemeral=True)
            print(f"Error in PartyRoleSelect.callback: {e}")

class PartyView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PartyRoleSelect())

@bot.command()
async def 모집(ctx):
    party_info["participants"].clear()

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        await ctx.send("📥 파티 정보를 한 줄로 입력해주세요.\n예시: `브리레흐1-3관 6/30 20:00`")
        msg = await bot.wait_for("message", timeout=30.0, check=check)
        parts = msg.content.strip().split()

        if len(parts) != 3:
            return await ctx.send("⚠️ 형식이 올바르지 않습니다. 예시: `브리레흐1-3관 6/30 20:00`")

        dungeon, date, time = parts

        party_info["dungeon"] = dungeon
        party_info["date"] = date
        party_info["time"] = time

        dt_str = f"2025-{date} {time}"
        party_time = datetime.strptime(dt_str, "%Y-%m/%d %H:%M")
        party_info["reminder_time"] = party_time - timedelta(minutes=30)

    except asyncio.TimeoutError:
        return await ctx.send("시간 초과! 다시 시도해주세요.")
    except Exception:
        return await ctx.send("⚠️ 날짜나 시간 형식이 잘못되었습니다. 예: `6/30`, `20:00`")

    thread = await ctx.channel.create_thread(
        name=f"{ctx.author.display_name}님의 파티 모집",
        type=discord.ChannelType.public_thread,
        auto_archive_duration=60,
    )
    party_info["thread"] = thread

    initial_description = (
        f"📍 던전: **{dungeon}**\n"
        f"📅 날짜: **{date}**\n"
        f"⏰ 시간: **{time}**\n\n"
        "**🧑‍🤝‍🧑 현재 참여자 명단:**\n(아직 없음)\n\n"
        "🔔 참여자에게 시작 30분 전에 알림이 전송됩니다!\n"
        "👇 아래 셀렉트 메뉴에서 역할을 선택해 파티에 참여하세요! 최대 8명 + 예비 인원 허용."
    )
    embed = discord.Embed(title="🎯 파티 모집중!", description=initial_description, color=0x00ff00)
    embed_msg = await thread.send(embed=embed)
    await embed_msg.pin()
    party_info["embed_msg"] = embed_msg

    view = PartyView()
    await thread.send(view=view)
    await ctx.send(f"{ctx.author.mention}님, 파티 모집 스레드가 생성되었습니다: {thread.mention}")

async def reminder_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now()
        if party_info["reminder_time"] and now >= party_info["reminder_time"]:
            if party_info["participants"]:
                mentions = " ".join(member.mention for member in party_info["participants"].keys())
                try:
                    await party_info["thread"].send(
                        f"⏰ **리마인더 알림!**\n"
                        f"{mentions}\n"
                        f"`{party_info['dungeon']}` 던전이 30분 후에 시작됩니다! ({party_info['date']} {party_info['time']})"
                    )
                except Exception as e:
                    print(f"리마인더 전송 실패: {e}")
            party_info["reminder_time"] = None
        await asyncio.sleep(600)  # 10분마다 체크

@bot.event
async def on_ready():
    print(f"✅ 봇 로그인 완료: {bot.user}")

    # 역할 선택 메시지 복구 및 뷰 재적용
    channel = bot.get_channel(ROLE_SELECT_CHANNEL_ID)
    if channel is None:
        print(f"❌ 역할 선택 채널({ROLE_SELECT_CHANNEL_ID})을 찾을 수 없습니다! 채널 ID를 확인해주세요.")
        return

    role_select_msg = None
    async for msg in channel.history(limit=100):
        if (
            msg.author == bot.user
            and msg.content == "안녕하세요! 아래 버튼을 눌러 역할을 추가하거나 제거할 수 있습니다."
        ):
            role_select_msg = msg
            break

    if role_select_msg is None:
        print("역할 선택 메시지가 없어 새로 생성합니다.")
        view = RoleSelectView()
        await channel.send("안녕하세요! 아래 버튼을 눌러 역할을 추가하거나 제거할 수 있습니다.", view=view)
    else:
        print("역할 선택 메시지를 찾았습니다. 뷰를 다시 붙입니다.")
        view = RoleSelectView()
        try:
            await role_select_msg.edit(view=view)
        except Exception as e:
            print(f"역할 선택 메시지 뷰 재적용 실패: {e}")

    # 파티 모집 메시지 복구 및 뷰 재적용
    party_channel = bot.get_channel(PARTY_RECRUIT_CHANNEL_ID)
    if party_channel is None:
        print(f"❌ 파티 모집 채널({PARTY_RECRUIT_CHANNEL_ID})을 찾을 수 없습니다! 채널 ID를 확인해주세요.")
    else:
        party_embed_msg = None
        async for msg in party_channel.history(limit=100):
            if (
                msg.author == bot.user
                and msg.embeds
                and msg.embeds[0].title == "🎯 파티 모집중!"
            ):
                party_embed_msg = msg
                break
        
        if party_embed_msg is None:
            print("파티 모집 메시지가 없어 새로 생성해야 합니다.")
            if party_info["dungeon"] and party_info["date"] and party_info["time"]:
                initial_description = (
                    f"📍 던전: **{party_info['dungeon']}**\n"
                    f"📅 날짜: **{party_info['date']}**\n"
                    f"⏰ 시간: **{party_info['time']}**\n\n"
                    "**🧑‍🤝‍🧑 현재 참여자 명단:**\n(아직 없음)\n\n"
                    "🔔 참여자에게 시작 30분 전에 알림이 전송됩니다!\n"
                    "👇 아래 셀렉트 메뉴에서 역할을 선택해 파티에 참여하세요! 최대 8명 + 예비 인원 허용."
                )
                embed = discord.Embed(title="🎯 파티 모집중!", description=initial_description, color=0x00ff00)
                embed_msg = await party_channel.send(embed=embed)
                await embed_msg.pin()
                party_info["embed_msg"] = embed_msg
                view = PartyView()
                await party_channel.send(view=view)
                print("파티 모집 메시지를 새로 생성했습니다.")
            else:
                print("파티 모집 정보가 없어 메시지 생성이 불가능합니다.")
        else:
            print("파티 모집 메시지를 찾았습니다. 뷰를 다시 붙입니다.")
            party_info["embed_msg"] = party_embed_msg
            view = PartyView()
            try:
                await party_embed_msg.edit(view=view)
            except Exception as e:
                print(f"파티 모집 메시지 뷰 재적용 실패: {e}")

    bot.loop.create_task(reminder_loop())

WELCOME_CHANNEL_ID = 1390643886656847983 # 🌊｜반갑죠 채널 ID로 변경

@bot.event
async def on_member_join(member):
    welcome_channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if welcome_channel:
        await welcome_channel.send(
            f"🟢 {member.mention} 님, 선택적 너드들 길드 디스코드 서버에 오신 것을 환영합니다!\n\n"
            "📌 서버 이용 안내는 이 채널에서 확인하세요!\n"
            f"💠 역할 선택은 <#{ROLE_SELECT_CHANNEL_ID}> 에서!\n"
            f"🎯 파티 모집은 <#{PARTY_RECRUIT_CHANNEL_ID}> 에서 확인하세요!\n\n"
            "즐거운 시간 되세요! 😄"
        )
    else:
        print(f"⚠️ 환영 채널을 찾을 수 없습니다. 채널 ID를 확인해주세요.")


@bot.event
async def on_member_remove(member):
    log_channel = discord.utils.get(member.guild.text_channels, name="🚪│입출입-로그")
    if log_channel:
        await log_channel.send(f"🔴 {member.display_name} 님이 서버를 퇴장했습니다.")

@bot.command()
async def 수정(ctx):
    if not party_info["thread"] or ctx.channel != party_info["thread"]:
        return await ctx.send("⚠️ 이 명령어는 파티 모집 스레드 안에서만 사용 가능해요.")

    await ctx.send("✏️ 수정할 정보를 입력해주세요 (예: `수정 던전명 날짜 시간`)\n예시: `수정 브리레흐2관 7/5 21:00`")

    def check(m): 
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", timeout=30.0, check=check)
        parts = msg.content.strip().split()
        if len(parts) != 4 or parts[0] != "수정":
            return await ctx.send("⚠️ 형식이 잘못되었습니다. 예: `수정 브리레흐2관 7/5 21:00`")

        _, dungeon, date, time = parts
        party_info["dungeon"] = dungeon
        party_info["date"] = date
        party_info["time"] = time

        dt_str = f"2025-{date} {time}"
        party_time = datetime.strptime(dt_str, "%Y-%m/%d %H:%M")
        party_info["reminder_time"] = party_time - timedelta(minutes=30)

        await ctx.send("\u2705 파티 정보가 수정되었습니다!")

        # embed 갱신
        desc_lines = [
            f"📍 던전: **{dungeon}**",
            f"📅 날짜: **{date}**",
            f"⏰ 시간: **{time}**",
            "",
            "**🧑‍🤝‍🧑 현재 참여자 명단:**",
        ]

        main_participants = list(party_info["participants"].items())[:8]
        reserve_participants = list(party_info["participants"].items())[8:]

        if main_participants:
            for member, role in main_participants:
                desc_lines.append(f"- {member.display_name}: {role}")
        else:
            desc_lines.append("(아직 없음)")

        if reserve_participants:
            desc_lines.append("\n**📄 예비 인원:**")
            for member, role in reserve_participants:
                desc_lines.append(f"- {member.display_name}: {role}")

        desc_lines.append("\n👇 셀렉트 메뉴에서 역할을 선택하거나 참여 취소를 해주세요! 최대 8명 + 예비 인원 허용.")

        embed = discord.Embed(title="🎯 파티 모집중!", description="\n".join(desc_lines), color=0x00ff00)
        if party_info["embed_msg"]:
            await party_info["embed_msg"].edit(embed=embed)

    except asyncio.TimeoutError:
        await ctx.send("시간 초과! 다시 시도해주세요.")

bot.run(TOKEN)
