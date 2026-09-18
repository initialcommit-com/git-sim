import sys
from git_sim.backend import m

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

        self.cmd += f"{type(self).__name__.lower()}{' -d' if self.d else ''} {self.name}{' ' + self.commit if self.commit else ''}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits()
        self.parse_all()
        self.center_frame_on_commit(self.get_commit())

        if not self.d:
            tagRec, tagText = self.ref_pill(self.name, self.theme.tag)

            commit = self.repo.commit(self.commit) if self.commit else self.get_commit()
            # Stack above whatever labels the commit already carries.
            top = self.stack_top(commit.hexsha)
            if top is None:
                print(
                    "git-sim error: can't create tag '"
                    + self.name
                    + "' on commit '"
                    + self.commit
                    + "', commit not in frame"
                )
                sys.exit(1)
            tagRec.next_to(top, m.UP)
            self.center_label(tagText, tagRec)

            fulltag = m.VGroup(tagRec, tagText)
            self.tag(fulltag, role="ref", name=self.name, kind="tag", phase="after")

            if settings.animate:
                self.play(m.Create(fulltag), run_time=1 / settings.speed)
            else:
                self.add(fulltag)

            self.toFadeOut.add(fulltag)
            self.drawnRefs[self.name] = fulltag
            self.add_ref_to_drawn_refs_by_commit(commit.hexsha, fulltag)
        else:
            self.remove_ref(self.name)

        self.recenter_frame()
        self.scale_frame()
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
