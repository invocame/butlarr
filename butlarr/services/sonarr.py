import math
from loguru import logger
from typing import Optional, List, Any, Literal
from dataclasses import dataclass, replace, field

from . import ArrService, ArrVariant, Action, ServiceContent, find_first, format_size
from .ext import ExtArrService
from ..tg_handler import command, callback, handler
from ..tg_handler.message import Response, repaint, clear
from ..tg_handler.auth import authorized
from ..tg_handler.session_state import sessionState, default_session_state_key_fn
from ..tg_handler.keyboard import Button, keyboard

RELEASES_PER_PAGE = 5


def _release_row1(r: dict) -> str:
    """First row: approval + quality + size (non-clickable header)."""
    approved = "✅" if r.get("approved") else "⚠️"
    quality = r.get("quality", {}).get("quality", {}).get("name", "?")
    size = format_size(r.get("size", 0))
    return f"{approved} {quality}  {size}"

def _release_row2_sp(r: dict) -> str:
    """Second row: seeders/peers label."""
    seeders = r.get("seeders")
    peers = r.get("leechers")
    if seeders is not None and peers is not None:
        return f"S:{seeders} P:{peers}"
    elif seeders is not None:
        return f"S:{seeders}"
    return "S:?"


@dataclass(frozen=True)
class SeasonState:
    available: List[int]
    selected: List[int]


@dataclass(frozen=True)
class State:
    items: List[Any]
    index: int
    quality_profile: Any
    language_profile: Any
    tags: List[str]
    root_folder: Any
    seasons: SeasonState
    menu: Optional[
        Literal["path"] | Literal["tags"] | Literal["quality"]
        | Literal["language"] | Literal["add"] | Literal["releases"]
    ]
    releases: Optional[List[Any]] = field(default=None)
    release_page: int = 0
    downloaded: List[int] = field(default_factory=list)
    info_msg_ids: List[int] = field(default_factory=list)


@handler
class Sonarr(ExtArrService, ArrService):
    def __init__(self, commands: List[str], api_host: str, api_key: str):
        self.commands = commands
        self.api_key = api_key

        self.api_version = self.detect_api(api_host)
        self.service_content = ServiceContent.SERIES
        self.arr_variant = ArrVariant.SONARR
        self.root_folders = self.get_root_folders()
        self.quality_profiles = self.get_quality_profiles()
        self.language_profiles = self.get_language_profiles()

        if not self.root_folders:
            logger.warning(
                "No root folders configured! Please configure root folders inside the "
                "Sonarr interface. Otherwise Butlarr might not behave as expected."
            )
        if not self.quality_profiles:
            logger.warning(
                "No quality profiles configured! Please configure quality profiles inside "
                "the Sonarr interface. Otherwise Butlarr might not behave as expected."
            )
        if not self.language_profiles:
            logger.warning(
                "No language profiles configured! Please configure language profiles inside "
                "the Sonarr interface. Otherwise Butlarr might not behave as expected."
            )

    def _get_season_state(self, item):
        available_seasons = [e.get("seasonNumber") for e in item.get("seasons", [])]
        return SeasonState(available=available_seasons, selected=[])

    @keyboard
    def keyboard(self, state: State):
        item = state.items[state.index]
        in_library = "id" in item and item["id"]

        rows_menu = []

        # ── Releases picker ───────────────────────────────────────────────────
        if state.menu == "releases":
            row_navigation = [Button("=== Available Releases ===", "noop")]
            releases = state.releases or []

            if not releases:
                rows_menu = [[Button("No releases found", "noop")]]
            else:
                total_pages = math.ceil(len(releases) / RELEASES_PER_PAGE)
                start = state.release_page * RELEASES_PER_PAGE
                page_releases = releases[start: start + RELEASES_PER_PAGE]

                rows_menu = []
                for i, r in enumerate(page_releases):
                    abs_idx = start + i
                    if abs_idx in state.downloaded:
                        rows_menu.append([Button(f"⬇️ {_release_row1(r)}", "noop")])
                        rows_menu.append([
                            Button(_release_row2_sp(r), "noop"),
                            Button("ℹ️", self.get_clbk("relinfo", abs_idx)),
                        ])
                    else:
                        rows_menu.append([Button(_release_row1(r), "noop")])
                        rows_menu.append([
                            Button(_release_row2_sp(r), "noop"),
                            Button("⬇️ Download", self.get_clbk("dlrelease", abs_idx)),
                            Button("ℹ️", self.get_clbk("relinfo", abs_idx)),
                        ])

                rows_menu.append([
                    (
                        Button("◀ Prev", self.get_clbk("relpage", state.release_page - 1))
                        if state.release_page > 0 else Button()
                    ),
                    Button(f"{state.release_page + 1} / {total_pages}", "noop"),
                    (
                        Button("Next ▶", self.get_clbk("relpage", state.release_page + 1))
                        if state.release_page + 1 < total_pages else Button()
                    ),
                ])

        # ── Add / edit menu ───────────────────────────────────────────────────
        elif state.menu == "add":
            row_navigation = [
                Button("=== Editing Series ===" if in_library else "=== Adding Series ===", "noop")
            ]
            rows_menu = [
                [Button(
                    f"Change Quality   ({state.quality_profile.get('name', '-')})",
                    self.get_clbk("quality", state.index),
                )],
                [Button(
                    f"Change Path   ({state.root_folder.get('path', '-')})",
                    self.get_clbk("path", state.index),
                )],
                [Button(
                    f"Change Language   ({state.language_profile.get('name', '-')})",
                    self.get_clbk("language", state.index),
                )],
            ]

        # ── Season search ─────────────────────────────────────────────────────
        elif state.menu == "seasons":
            row_navigation = [Button("=== Search for Seasons ===")]
            rows_menu = [
                [Button(
                    f"{'✔' if sid in state.seasons.selected else '🔍'} Season {sid}",
                    self.get_clbk("noop" if sid in state.seasons.selected else "searchseason", sid),
                )]
                for sid in state.seasons.available
            ]

        # ── Path selector ─────────────────────────────────────────────────────
        elif state.menu == "path":
            row_navigation = [Button("=== Selecting Root Folder ===")]
            rows_menu = [
                [Button(p.get("path", "-"), self.get_clbk("selectpath", p.get("id")))]
                for p in self.root_folders
            ]

        # ── Quality selector ──────────────────────────────────────────────────
        elif state.menu == "quality":
            row_navigation = [Button("=== Selecting Quality Profile ===")]
            rows_menu = [
                [Button(p.get("name", "-"), self.get_clbk("selectquality", p.get("id")))]
                for p in self.quality_profiles
            ]

        # ── Language selector ─────────────────────────────────────────────────
        elif state.menu == "language":
            row_navigation = [Button("=== Selecting Language Profile ===")]
            rows_menu = [
                [Button(p.get("name", "-"), self.get_clbk("selectlanguage", p.get("id")))]
                for p in self.language_profiles
            ]

        # ── Default view ──────────────────────────────────────────────────────
        else:
            if in_library:
                monitored = item.get("monitored", True)
                missing = not item.get("hasFile", False)
                rows_menu = [
                    [Button("🔍 Search for Seasons", self.get_clbk("seasons", state.index))],
                    [
                        Button("📺 Monitored" if monitored else "Unmonitored"),
                        Button("💾 Missing" if missing else "Downloaded"),
                    ],
                ]
            row_navigation = [
                (
                    Button("⬅ Prev", self.get_clbk("goto", state.index - 1))
                    if state.index > 0 else Button()
                ),
                (
                    Button("TVDB", url=f"https://www.thetvdb.com/?id={item['tvdbId']}&tab=series")
                    if item.get("tvdbId") else None
                ),
                (
                    Button("IMDB", url=f"https://imdb.com/title/{item['imdbId']}")
                    if item.get("imdbId") else None
                ),
                (
                    Button("Next ➡", self.get_clbk("goto", state.index + 1))
                    if state.index < len(state.items) - 1 else Button()
                ),
            ]

        # ── Action rows ───────────────────────────────────────────────────────
        rows_action = []
        if in_library:
            if state.menu == "releases":
                rows_action.append([Button("✅ Done", self.get_clbk("done"))])
            elif state.menu == "add":
                rows_action.append([
                    Button("🗑 Remove", self.get_clbk("remove")),
                    Button("✅ Submit", self.get_clbk("add", "no-search")),
                ])
                rows_action.append([
                    Button("✅ + 🔍 Submit & Search", self.get_clbk("add", "search")),
                ])
            else:
                rows_action.append([
                    Button("🎯 Pick Release", self.get_clbk("releases")),
                ])
                rows_action.append([
                    Button("🗑 Remove", self.get_clbk("remove")),
                    Button("✏️ Edit", self.get_clbk("addmenu")),
                ])
        else:
            if not state.menu:
                rows_action.append([Button("➕ Add", self.get_clbk("addmenu"))])
            elif state.menu == "add":
                rows_action.append([
                    Button("📚 Add (No Monitor)", self.get_clbk("add", "no-monitor")),
                ])
                rows_action.append([
                    Button("📺 Monitor All", self.get_clbk("add", "no-search")),
                    Button("🔍 Monitor & Search", self.get_clbk("add", "search")),
                ])
                rows_action.append([
                    Button("🎯 Monitor & Pick", self.get_clbk("monitorpick")),
                ])
            elif state.menu == "releases":
                rows_action.append([Button("✅ Done", self.get_clbk("done"))])

        back_target = (
            "goto" if state.menu in ("seasons", "add", "releases")
            else "addmenu" if state.menu else "goto"
        )
        if state.menu and state.menu != "releases":
            rows_action.append([Button("🔙 Back", self.get_clbk(back_target))])
        elif not state.menu:
            rows_action.append([Button("❌ Cancel", self.get_clbk("cancel"))])

        return [row_navigation, *rows_menu, *rows_action]

    def create_message(self, state: State, full_redraw=False):
        if not state.items:
            return Response(caption="No series found", state=state)

        item = state.items[state.index]
        keyboard_markup = self.keyboard(state)

        reply_message = f"{item['title']} "
        if item["year"] and str(item["year"]) not in item["title"]:
            reply_message += f"({item['year']}) "
        if item["runtime"]:
            reply_message += f"{item['runtime']}min "
        reply_message += f"- {item['status'].title()}\n\n{item.get('overview', '')}"
        reply_message = reply_message[:1024]

        cover_url = item.get("remotePoster")
        if not cover_url and item.get("images"):
            cover_url = item["images"][0]["remoteUrl"]

        return Response(
            photo=cover_url if full_redraw else None,
            caption=reply_message,
            reply_markup=keyboard_markup,
            state=state,
        )

    def _get_initial_state(self, items):
        return State(
            items=items,
            index=0,
            root_folder=(
                find_first(
                    self.root_folders,
                    lambda x: items[0].get("folderName", "").startswith(x.get("path")),
                ) if items else None
            ),
            quality_profile=(
                find_first(
                    self.quality_profiles,
                    lambda x: items[0].get("qualityProfileId") == x.get("id"),
                ) if items else None
            ),
            language_profile=(
                find_first(
                    self.language_profiles,
                    lambda x: items[0].get("languageProfileId") == x.get("id"),
                ) if items else None
            ),
            tags=items[0].get("tags", []) if items else [],
            menu=None,
            seasons=self._get_season_state(items[0]) if items else SeasonState([], []),
            releases=None,
            release_page=0,
            downloaded=[],
        )

    # ── Commands ──────────────────────────────────────────────────────────────

    @repaint
    @command(
        default=True,
        default_pattern="<title>",
        default_description="Search for a series",
        cmds=[("search", "<title>", "Search for a series")],
    )
    @sessionState(init=True)
    @authorized
    async def cmd_default(self, update, context, args):
        if len(args) > 1 and args[0] == "search":
            args = args[1:]
        title = " ".join(args)
        items = self.lookup(title)
        state = self._get_initial_state(items)
        self.session_db.add_session_entry(default_session_state_key_fn(self, update), state)
        return self.create_message(state, full_redraw=True)

    @command(cmds=[("help", "", "Shows only the sonarr help page")])
    async def cmd_help(self, update, context, args):
        return await ExtArrService.cmd_help(self, update, context, args)

    @repaint
    @command(cmds=[("queue", "", "Shows the sonarr download queue")])
    @authorized
    async def cmd_queue(self, update, context, args):
        return await ExtArrService.cmd_queue(self, update, context, args)

    @repaint
    @callback(cmds=["queue"])
    @authorized
    async def clbk_queue(self, update, context, args):
        return await ExtArrService.clbk_queue(self, update, context, args)

    @repaint
    @command(cmds=[("list", "", "List all series in the library")])
    @authorized
    async def cmd_list(self, update, context, args):
        items = self.list_()
        state = self._get_initial_state(items)
        self.session_db.add_session_entry(default_session_state_key_fn(self, update), state)
        return self.create_message(state, full_redraw=True)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    @repaint
    @callback(cmds=[
        "goto", "tags", "addtag", "remtag", "seasons", "searchseason",
        "path", "selectpath", "quality", "selectquality",
        "language", "selectlanguage", "addmenu",
    ])
    @sessionState()
    @authorized
    async def clbk_update(self, update, context, args, state):
        full_redraw = False
        if args[0] == "goto":
            if len(args) > 1:
                idx = int(args[1])
                item = state.items[idx]
                state = replace(
                    state,
                    index=idx,
                    root_folder=find_first(
                        self.root_folders,
                        lambda x: item.get("folderName", "").startswith(x.get("path")),
                    ),
                    quality_profile=find_first(
                        self.quality_profiles,
                        lambda x: item.get("qualityProfileId") == x.get("id"),
                    ),
                    tags=item.get("tags", []),
                    menu=None,
                    seasons=self._get_season_state(item),
                    releases=None,
                    release_page=0,
                    downloaded=[],
                    info_msg_ids=[],
                )
                full_redraw = True
            else:
                state = replace(state, menu=None, releases=None, release_page=0, downloaded=[], info_msg_ids=[])
        elif args[0] == "seasons":
            state = replace(state, menu="seasons")
        elif args[0] == "searchseason":
            item = state.items[state.index]
            self.request(
                "command",
                action=Action.POST,
                params={
                    "name": "SeasonSearch",
                    "seriesId": item.get("id"),
                    "seasonNumber": int(args[1]),
                },
            )
            season_state = replace(state.seasons, selected=[*state.seasons.selected, int(args[1])])
            state = replace(state, seasons=season_state)
        elif args[0] == "tags":
            state = replace(state, tags=[], menu="tags")
        elif args[0] == "addtag":
            state = replace(state, tags=[*state.tags, args[1]])
        elif args[0] == "remtag":
            state = replace(state, tags=[t for t in state.tags if t != args[1]])
        elif args[0] == "path":
            state = replace(state, menu="path")
        elif args[0] == "selectpath":
            path = self.get_root_folder(args[1])
            state = replace(state, root_folder=path, menu="add")
        elif args[0] == "quality":
            state = replace(state, menu="quality")
        elif args[0] == "selectquality":
            quality_profile = self.get_quality_profile(args[1])
            state = replace(state, quality_profile=quality_profile, menu="add")
        elif args[0] == "language":
            state = replace(state, menu="language")
        elif args[0] == "selectlanguage":
            language_profile = self.get_language_profile(args[1])
            state = replace(state, language_profile=language_profile, menu="add")
        elif args[0] == "addmenu":
            state = replace(state, menu="add")

        return self.create_message(state, full_redraw=full_redraw)

    @repaint
    @callback(cmds=["releases", "relpage"])
    @sessionState()
    @authorized
    async def clbk_releases(self, update, context, args, state):
        if args[0] == "releases":
            item = state.items[state.index]
            releases = self.get_releases(seriesId=item["id"])
            state = replace(state, menu="releases", releases=releases, release_page=0, downloaded=[], info_msg_ids=[])
        elif args[0] == "relpage":
            state = replace(state, release_page=int(args[1]))
        return self.create_message(state)

    @repaint
    @callback(cmds=["monitorpick"])
    @sessionState()
    @authorized
    async def clbk_monitorpick(self, update, context, args, state):
        result = self.add(
            item=state.items[state.index],
            quality_profile_id=state.quality_profile.get("id", 0),
            language_profile_id=state.language_profile.get("id", 0),
            root_folder_path=state.root_folder.get("path", ""),
            tags=state.tags,
            options={
                "addOptions": {
                    "searchForMissingEpisodes": False,
                    "monitor": "all",
                },
            },
        )
        if not result:
            return Response(caption="Could not add the series.", state=state)

        new_items = list(state.items)
        new_items[state.index] = result
        releases = self.get_releases(seriesId=result["id"])
        state = replace(
            state,
            items=new_items,
            menu="releases",
            releases=releases,
            release_page=0,
            downloaded=[],
            info_msg_ids=[],
            seasons=self._get_season_state(result),
        )
        self.session_db.add_session_entry(default_session_state_key_fn(self, update), state)
        return self.create_message(state, full_redraw=True)

    @repaint
    @callback(cmds=["dlrelease"])
    @sessionState()
    @authorized
    async def clbk_dlrelease(self, update, context, args, state):
        idx = int(args[1])
        releases = state.releases or []
        if idx >= len(releases):
            return Response(caption="Release no longer available.", state=state)

        release = releases[idx]
        result = self.download_release(
            guid=release["guid"],
            indexer_id=release.get("indexerId", 0),
        )
        if not result:
            return Response(caption="Something went wrong — could not start the download.", state=state)

        state = replace(state, downloaded=[*state.downloaded, idx])
        return self.create_message(state)

    @repaint
    @callback(cmds=["add"])
    @sessionState()
    @authorized
    async def clbk_add(self, update, context, args, state):
        result = self.add(
            item=state.items[state.index],
            quality_profile_id=state.quality_profile.get("id", 0),
            language_profile_id=state.language_profile.get("id", 0),
            root_folder_path=state.root_folder.get("path", ""),
            tags=state.tags,
            options={
                "addOptions": {
                    "searchForMissingEpisodes": args[1] == "search",
                    "monitor": "none" if args[1] == "no-monitor" else "all",
                },
            },
        )
        if not result:
            return Response(caption="Seems like something went wrong...", state=state)

        # Update the item in state with the full result (now has an ID assigned by Sonarr)
        new_items = list(state.items)
        new_items[state.index] = result
        state = replace(
            state,
            items=new_items,
            menu=None,
            releases=None,
            release_page=0,
            seasons=self._get_season_state(result),
        )
        self.session_db.add_session_entry(default_session_state_key_fn(self, update), state)
        return self.create_message(state, full_redraw=True)

    @callback(cmds=["relinfo"])
    @authorized
    async def clbk_relinfo(self, update, context, args):
        key = default_session_state_key_fn(self, update)
        state = self.session_db.get_session_entry(key)

        idx = int(args[1])
        releases = state.releases or []
        if idx >= len(releases):
            await update.callback_query.answer()
            return

        r = releases[idx]
        title = r.get("title", "Unknown")
        quality = r.get("quality", {}).get("quality", {}).get("name", "?")
        size = format_size(r.get("size", 0))
        seeders = r.get("seeders")
        peers = r.get("leechers")
        indexer = r.get("indexer", "?")
        approved = "✅ Approved" if r.get("approved") else "⚠️ Not approved"

        lines = [
            f"📄 *Release info*",
            f"`{title}`",
            f"",
            f"Quality: {quality}",
            f"Size: {size}",
        ]
        if seeders is not None:
            lines.append(f"Seeders: {seeders}  Peers: {peers if peers is not None else '?'}")
        lines += [
            f"Indexer: {indexer}",
            f"Status: {approved}",
        ]
        if r.get("rejections"):
            lines.append(f"Rejections: {', '.join(r['rejections'])}")

        chat_id = update.callback_query.message.chat_id
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            parse_mode="Markdown",
        )
        await update.callback_query.answer()

        new_state = replace(state, info_msg_ids=[*state.info_msg_ids, msg.message_id])
        self.session_db.add_session_entry(key, new_state)

    @clear
    @callback(cmds=["done"])
    @sessionState(clear=True)
    @authorized
    async def clbk_done(self, update, context, args, state):
        # Delete all info messages
        chat_id = update.callback_query.message.chat_id
        for mid in state.info_msg_ids or []:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass

        downloaded = state.downloaded or []
        releases = state.releases or []
        if not downloaded:
            return Response(caption="No releases were downloaded.")
        lines = [f"⬇️ Download started for {len(downloaded)} release(s):\n"]
        for idx in downloaded:
            if idx < len(releases):
                r = releases[idx]
                quality = r.get("quality", {}).get("quality", {}).get("name", "?")
                size = format_size(r.get("size", 0))
                title = r.get("title", "Unknown")[:50]
                lines.append(f"• {quality}  {size}\n  {title}")
        return Response(caption="\n".join(lines))

    @clear
    @callback(cmds=["cancel"])
    @sessionState(clear=True)
    @authorized
    async def clbk_cancel(self, update, context, args, state):
        return Response(caption="Search canceled!")

    @clear
    @callback(cmds=["remove"])
    @sessionState(clear=True)
    @authorized
    async def clbk_remove(self, update, context, args, state):
        self.remove(id=state.items[state.index].get("id"))
        return Response(caption="Series removed!")