"""The client window: Archipelago's own (or Universal Tracker's) plus a "Weapon Buffs" tab."""

NO_BUFFS = "No weapon buffs received yet."


def buff_lines(levels: list[tuple[str, int, int, int, int]]) -> str:
    """levels comes from game_state.weapon_buff_levels (already in alphabetical order)."""
    if not levels:
        return NO_BUFFS
    return "\n".join(
        f"{name}   x{have} of {most}   ({normal} -> {now})"
        for name, have, most, normal, now in levels
    )


def make_gui(base_class: type) -> type:
    from kivy.metrics import dp
    from kivymd.uix.label import MDLabel
    from kivymd.uix.scrollview import MDScrollView

    class Ts2Manager(base_class):
        def build(self):
            container = super().build()
            try:
                self.weapon_buffs_label = MDLabel(text=NO_BUFFS, halign="left", adaptive_height=True,
                                                  padding=(dp(12), dp(12)))
                scroll = MDScrollView()
                scroll.add_widget(self.weapon_buffs_label)
                self.add_client_tab("Weapon Buffs", scroll)
            except Exception:
                self.weapon_buffs_label = None      # an older Archipelago: carry on without the tab
            return container

        def update_weapon_buffs(self, levels) -> None:
            if getattr(self, "weapon_buffs_label", None) is not None:
                self.weapon_buffs_label.text = buff_lines(levels)

    return Ts2Manager
