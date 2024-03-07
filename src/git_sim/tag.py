import sys
import manim as m

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Tag(GitSimBaseCommand):
    def __init__(self, name: str, commit: str, d: bool):
        super().__init__()
        self.name = name
        self.commit = commit
        self.d = d

        if self.d:
            if self.commit:
                print(
                    "git-sim error: can't specify commit '"
                    + self.commit
                    + "', when using -d flag"
                )
                sys.exit(1)
            if self.name not in self.repo.tags:
                print(
                    "git-sim error: can't delete tag '"
                    + self.name
                    + "', tag doesn't exist"
                )
                sys.exit(1)
        else:
            if self.name in self.repo.tags:
                print(
                    "git-sim error: can't create tag '"
                    + self.name
                    + "', tag already exists"
                )
                sys.exit(1)

        self.cmd += f"{type(self).__name__.lower()}{' -d' if self.d else ''}{' self.commit' if self.commit else ''} {self.name}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits()
        self.parse_all()
        self.center_frame_on_commit(self.get_commit())

        if not self.d:
            tagText = m.Text(
                self.name,
                font=self.font,
                font_size=20,
                color=self.fontColor,
            )
            tagRec = m.Rectangle(
                color=m.YELLOW,
                fill_color=m.YELLOW,
                fill_opacity=0.25,
                height=0.4,
                width=tagText.width + 0.25,
            )
            
            if self.commit:
                commit = self.repo.commit(self.commit)
                try:
                    tagRec.next_to(self.drawnRefsByCommit[commit.hexsha][-1], m.UP)
                except KeyError:
                    try:
                        tagRec.next_to(self.drawnCommitIds[commit.hexsha], m.UP)
                    except KeyError:
                        print(
                            "git-sim error: can't create tag '"
                            + self.name
                            + "' on commit '"
                            + self.commit
                            + "', commit not in frame"
                        )
                        sys.exit(1)
            else:
                tagRec.next_to(self.topref, m.UP)
            tagText.move_to(tagRec.get_center())

            fulltag = m.VGroup(tagRec, tagText)

            if settings.animate:
                self.play(m.Create(fulltag), run_time=1 / settings.speed)
            else:
                self.add(fulltag)

            self.toFadeOut.add(tagRec, tagText)
            self.drawnRefs[self.name] = fulltag
        else:
            fulltag = self.drawnRefs[self.name]
            if settings.animate:
                self.play(m.Uncreate(fulltag), run_time=1 / settings.speed)
            else:
                self.remove(fulltag)

        self.recenter_frame()
        self.scale_frame()
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
