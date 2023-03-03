import platform
import sys

import git
import manim as m
import numpy
from git.exc import GitCommandError, InvalidGitRepositoryError
from git.repo import Repo

from git_sim.settings import settings


class GitSimBaseCommand(m.MovingCameraScene):
    def __init__(self):
        super().__init__()
        self.init_repo()

        self.fontColor = m.BLACK if settings.light_mode else m.WHITE
        self.drawnCommits = {}
        self.drawnRefs = {}
        self.drawnCommitIds = {}
        self.toFadeOut = m.Group()
        self.prevRef = None
        self.topref = None
        self.n_default = settings.n_default
        self.n = settings.n
        self.n_orig = self.n
        self.selected_branches = []
        self.zone_title_offset = 2.6 if platform.system() == "Windows" else 2.6
        self.arrow_map = []
        self.all = settings.all
        self.first_parse = True

        self.logo = m.ImageMobject(settings.logo)
        self.logo.width = 3

    def init_repo(self):
        try:
            self.repo = Repo(search_parent_directories=True)
        except InvalidGitRepositoryError:
            print("git-sim error: No Git repository found at current path.")
            sys.exit(1)

    def construct(self):
        print(f"{settings.INFO_STRING} {type(self).__name__.lower()}")
        self.show_intro()
        self.parse_commits()
        self.fadeout()
        self.show_outro()

    def get_commit(self, sha_or_ref="HEAD"):
        return self.repo.commit(sha_or_ref)

    def get_default_commits(self):
        defaultCommits = [self.get_commit()]
        for x in range(self.n_default - 1):
            defaultCommits.append(defaultCommits[-1].parents[0])
        return defaultCommits

    def parse_commits(
        self,
        commit=None,
        i=0,
        prevCircle=None,
        shift=numpy.array([0.0, 0.0, 0.0]),
    ):
        commit = commit or self.get_commit()

        isNewCommit = commit.hexsha not in self.drawnCommits

        if i < self.n:
            commitId, circle, arrow, hide_refs = self.draw_commit(
                commit, i, prevCircle, shift
            )

            if commit != "dark":
                if not hide_refs and isNewCommit:
                    self.draw_head(commit, i, commitId)
                    self.draw_branch(commit, i)
                    self.draw_tag(commit, i)
                if (
                    not isinstance(arrow, m.CurvedArrow)
                    and [arrow.start.tolist(), arrow.end.tolist()] not in self.arrow_map
                ):
                    self.draw_arrow(prevCircle, arrow)
                    self.arrow_map.append([arrow.start.tolist(), arrow.end.tolist()])
                elif (
                    isinstance(arrow, m.CurvedArrow)
                    and [arrow.get_start().tolist(), arrow.get_end().tolist()]
                    not in self.arrow_map
                ):
                    self.draw_arrow(prevCircle, arrow)
                    self.arrow_map.append(
                        [arrow.get_start().tolist(), arrow.get_end().tolist()]
                    )
                if i == 0 and len(self.drawnRefs) < 2:
                    self.draw_dark_ref()

            self.first_parse = False
            i += 1
            commitParents = list(commit.parents)
            if len(commitParents) > 0:
                if settings.invert_branches:
                    commitParents.reverse()

                if settings.hide_merged_branches:
                    self.parse_commits(commitParents[0], i, circle)
                else:
                    for p in range(len(commitParents)):
                        self.parse_commits(commitParents[p], i, circle)

    def parse_all(self):
        if self.all:
            for branch in self.get_nonparent_branch_names():
                self.parse_commits(self.get_commit(branch.name))

    def show_intro(self):
        if settings.animate and settings.show_intro:
            self.add(self.logo)

            initialCommitText = m.Text(
                settings.title,
                font="Monospace",
                font_size=36,
                color=self.fontColor,
            ).to_edge(m.UP, buff=1)
            self.add(initialCommitText)
            self.wait(2)
            self.play(m.FadeOut(initialCommitText))
            self.play(
                self.logo.animate.scale(0.25)
                .to_edge(m.UP, buff=0)
                .to_edge(m.RIGHT, buff=0)
            )

            self.camera.frame.save_state()
            self.play(m.FadeOut(self.logo))

        else:
            self.logo.scale(0.25).to_edge(m.UP, buff=0).to_edge(m.RIGHT, buff=0)
            self.camera.frame.save_state()

    def show_outro(self):
        if settings.animate and settings.show_outro:
            self.play(m.Restore(self.camera.frame))

            self.play(self.logo.animate.scale(4).set_x(0).set_y(0))

            outroTopText = m.Text(
                settings.outro_top_text,
                font="Monospace",
                font_size=36,
                color=self.fontColor,
            ).to_edge(m.UP, buff=1)
            self.play(m.AddTextLetterByLetter(outroTopText))

            outroBottomText = m.Text(
                settings.outro_bottom_text,
                font="Monospace",
                font_size=36,
                color=self.fontColor,
            ).to_edge(m.DOWN, buff=1)
            self.play(m.AddTextLetterByLetter(outroBottomText))

            self.wait(3)

    def fadeout(self):
        if settings.animate:
            self.wait(3)
            self.play(m.FadeOut(self.toFadeOut), run_time=1 / settings.speed)
        else:
            self.wait(0.1)

    def get_centers(self):
        centers = []
        for commit in self.drawnCommits.values():
            centers.append(commit.get_center())
        return centers

    def draw_commit(self, commit, i, prevCircle, shift=numpy.array([0.0, 0.0, 0.0])):
        if commit == "dark":
            commitFill = m.WHITE if settings.light_mode else m.BLACK
        elif len(commit.parents) <= 1:
            commitFill = m.RED
        else:
            commitFill = m.GRAY

        circle = m.Circle(
            stroke_color=commitFill, fill_color=commitFill, fill_opacity=0.25
        )
        circle.height = 1

        if shift.any():
            circle.shift(shift)

        if prevCircle:
            circle.next_to(
                prevCircle, m.RIGHT if settings.reverse else m.LEFT, buff=1.5
            )

        while any((circle.get_center() == c).all() for c in self.get_centers()):
            circle.shift(m.DOWN * 4)

        isNewCommit = commit.hexsha not in self.drawnCommits

        if isNewCommit:
            start = (
                prevCircle.get_center()
                if prevCircle
                else (m.LEFT if settings.reverse else m.RIGHT)
            )
            end = circle.get_center()
        else:
            circle.move_to(self.drawnCommits[commit.hexsha].get_center())
            start = (
                prevCircle.get_center()
                if prevCircle
                else (m.LEFT if settings.reverse else m.RIGHT)
            )
            end = self.drawnCommits[commit.hexsha].get_center()

        arrow = m.Arrow(start, end, color=self.fontColor)

        if commit == "dark":
            arrow = m.Arrow(
                start, end, color=m.WHITE if settings.light_mode else m.BLACK
            )

        length = numpy.linalg.norm(start - end) - (1.5 if start[1] == end[1] else 3)
        arrow.set_length(length)
        angle = arrow.get_angle()
        lineRect = (
            m.Rectangle(height=0.1, width=length, color="#123456")
            .move_to(arrow.get_center())
            .rotate(angle)
        )

        for commitCircle in self.drawnCommits.values():
            inter = m.Intersection(lineRect, commitCircle)
            if inter.has_points():
                arrow = m.CurvedArrow(start, end, color=self.fontColor)
                if start[1] == end[1]:
                    arrow.shift(m.UP * 1.25)
                if start[0] < end[0] and start[1] == end[1]:
                    arrow.flip(m.RIGHT).shift(m.UP)

        commitId, commitMessage, commit, hide_refs = self.build_commit_id_and_message(
            commit, i
        )
        commitId.next_to(circle, m.UP)

        if commit != "dark":
            self.drawnCommitIds[commit.hexsha] = commitId

        message = m.Text(
            "\n".join(
                commitMessage[j : j + 20] for j in range(0, len(commitMessage), 20)
            )[:100],
            font="Monospace",
            font_size=14,
            color=self.fontColor,
        ).next_to(circle, m.DOWN)

        if settings.animate and commit != "dark" and isNewCommit:
            self.play(
                self.camera.frame.animate.move_to(circle.get_center()),
                m.Create(circle),
                m.AddTextLetterByLetter(commitId),
                m.AddTextLetterByLetter(message),
                run_time=1 / settings.speed,
            )
        elif isNewCommit:
            self.add(circle, commitId, message)
        else:
            return commitId, circle, arrow, hide_refs

        if commit != "dark":
            self.drawnCommits[commit.hexsha] = circle

        self.toFadeOut.add(circle, commitId, message)
        self.prevRef = commitId

        return commitId, circle, arrow, hide_refs

    def get_nonparent_branch_names(self):
        branches = [b for b in self.repo.heads if not b.name.startswith("remotes/")]
        exclude = []
        for b1 in branches:
            for b2 in branches:
                if b1.name != b2.name:
                    if self.repo.is_ancestor(b1.commit, b2.commit):
                        exclude.append(b1.name)
        return [b for b in branches if b.name not in exclude]

    def build_commit_id_and_message(self, commit, i):
        hide_refs = False
        if commit == "dark":
            commitId = m.Text("", font="Monospace", font_size=20, color=self.fontColor)
            commitMessage = ""
        else:
            commitId = m.Text(
                commit.hexsha[0:6],
                font="Monospace",
                font_size=20,
                color=self.fontColor,
            )
            commitMessage = commit.message.split("\n")[0][:40].replace("\n", " ")
        return commitId, commitMessage, commit, hide_refs

    def draw_head(self, commit, i, commitId):
        if commit.hexsha == self.repo.head.commit.hexsha:
            headbox = m.Rectangle(color=m.BLUE, fill_color=m.BLUE, fill_opacity=0.25)
            headbox.width = 1
            headbox.height = 0.4
            headbox.next_to(commitId, m.UP)
            headText = m.Text(
                "HEAD", font="Monospace", font_size=20, color=self.fontColor
            ).move_to(headbox.get_center())

            head = m.VGroup(headbox, headText)

            if settings.animate:
                self.play(m.Create(head), run_time=1 / settings.speed)
            else:
                self.add(head)

            self.toFadeOut.add(head)
            self.drawnRefs["HEAD"] = head
            self.prevRef = head

            if i == 0 and self.first_parse:
                self.topref = self.prevRef

    def draw_branch(self, commit, i):
        x = 0

        remote_tracking_branches = self.get_remote_tracking_branches()

        branches = [branch.name for branch in self.repo.heads] + list(
            remote_tracking_branches.keys()
        )

        for selected_branch in self.selected_branches:
            branches.insert(0, branches.pop(branches.index(selected_branch)))

        for branch in branches:
            if (
                not self.is_remote_tracking_branch(branch)  # local branch
                and commit.hexsha == self.repo.heads[branch].commit.hexsha
            ) or (
                self.is_remote_tracking_branch(branch)  # remote tracking branch
                and commit.hexsha == remote_tracking_branches[branch]
            ):
                branchText = m.Text(
                    branch, font="Monospace", font_size=20, color=self.fontColor
                )
                branchRec = m.Rectangle(
                    color=m.GREEN,
                    fill_color=m.GREEN,
                    fill_opacity=0.25,
                    height=0.4,
                    width=branchText.width + 0.25,
                )

                branchRec.next_to(self.prevRef, m.UP)
                branchText.move_to(branchRec.get_center())

                fullbranch = m.VGroup(branchRec, branchText)

                self.prevRef = fullbranch

                if settings.animate:
                    self.play(m.Create(fullbranch), run_time=1 / settings.speed)
                else:
                    self.add(fullbranch)

                self.toFadeOut.add(branchRec, branchText)
                self.drawnRefs[branch] = fullbranch

                if i == 0 and self.first_parse:
                    self.topref = self.prevRef

                x += 1
                if x >= settings.max_branches_per_commit:
                    return

    def draw_tag(self, commit, i):
        x = 0

        if settings.hide_first_tag and i == 0:
            return

        for tag in self.repo.tags:
            try:
                if commit.hexsha == tag.commit.hexsha:
                    tagText = m.Text(
                        tag.name,
                        font="Monospace",
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

                    tagRec.next_to(self.prevRef, m.UP)
                    tagText.move_to(tagRec.get_center())

                    self.prevRef = tagRec

                    if settings.animate:
                        self.play(
                            m.Create(tagRec),
                            m.Create(tagText),
                            run_time=1 / settings.speed,
                        )
                    else:
                        self.add(tagRec, tagText)

                    self.toFadeOut.add(tagRec, tagText)

                    if i == 0 and self.first_parse:
                        self.topref = self.prevRef

                    x += 1
                    if x >= settings.max_tags_per_commit:
                        return
            except ValueError:
                pass

    def draw_arrow(self, prevCircle, arrow):
        if prevCircle:
            if settings.animate:
                self.play(m.Create(arrow), run_time=1 / settings.speed)
            else:
                self.add(arrow)

            self.toFadeOut.add(arrow)

    def recenter_frame(self):
        if settings.animate:
            self.play(
                self.camera.frame.animate.move_to(self.toFadeOut.get_center()),
                run_time=1 / settings.speed,
            )
        else:
            self.camera.frame.move_to(self.toFadeOut.get_center())

    def scale_frame(self):
        if settings.animate:
            self.play(
                self.camera.frame.animate.scale_to_fit_width(
                    self.toFadeOut.get_width() * 1.1
                ),
                run_time=1 / settings.speed,
            )
            if self.toFadeOut.get_height() >= self.camera.frame.get_height():
                self.play(
                    self.camera.frame.animate.scale_to_fit_height(
                        self.toFadeOut.get_height() * 1.25
                    ),
                    run_time=1 / settings.speed,
                )
        else:
            self.camera.frame.scale_to_fit_width(self.toFadeOut.get_width() * 1.1)
            if self.toFadeOut.get_height() >= self.camera.frame.get_height():
                self.camera.frame.scale_to_fit_height(
                    self.toFadeOut.get_height() * 1.25
                )

    def vsplit_frame(self):
        if settings.animate:
            self.play(
                self.camera.frame.animate.scale_to_fit_height(
                    self.camera.frame.get_height() * 2
                )
            )
        else:
            self.camera.frame.scale_to_fit_height(self.camera.frame.get_height() * 2)

        try:
            if settings.animate:
                self.play(
                    self.toFadeOut.animate.align_to(self.camera.frame, m.UP).shift(
                        m.DOWN * 0.75
                    )
                )
            else:
                self.toFadeOut.align_to(self.camera.frame, m.UP).shift(m.DOWN * 0.75)
        except ValueError:
            pass

    def setup_and_draw_zones(
        self,
        first_column_name="Untracked files",
        second_column_name="Working directory mods",
        third_column_name="Staging area",
        reverse=False,
    ):
        horizontal = m.Line(
            (
                self.camera.frame.get_left()[0],
                self.camera.frame.get_center()[1],
                0,
            ),
            (
                self.camera.frame.get_right()[0],
                self.camera.frame.get_center()[1],
                0,
            ),
            color=self.fontColor,
        ).shift(m.UP * 2.5)
        horizontal2 = m.Line(
            (
                self.camera.frame.get_left()[0],
                self.camera.frame.get_center()[1],
                0,
            ),
            (
                self.camera.frame.get_right()[0],
                self.camera.frame.get_center()[1],
                0,
            ),
            color=self.fontColor,
        ).shift(m.UP * 1.5)
        vert1 = m.DashedLine(
            (
                self.camera.frame.get_left()[0],
                self.camera.frame.get_bottom()[1],
                0,
            ),
            (self.camera.frame.get_left()[0], horizontal.get_start()[1], 0),
            dash_length=0.2,
            color=self.fontColor,
        ).shift(m.RIGHT * 8)
        vert2 = m.DashedLine(
            (
                self.camera.frame.get_right()[0],
                self.camera.frame.get_bottom()[1],
                0,
            ),
            (self.camera.frame.get_right()[0], horizontal.get_start()[1], 0),
            dash_length=0.2,
            color=self.fontColor,
        ).shift(m.LEFT * 8)

        if reverse:
            first_column_name = "Staging area"
            third_column_name = "Deleted changes"

        firstColumnTitle = (
            m.Text(
                first_column_name,
                font="Monospace",
                font_size=28,
                color=self.fontColor,
            )
            .move_to((vert1.get_center()[0] - 4, 0, 0))
            .shift(m.UP * self.zone_title_offset)
        )
        secondColumnTitle = (
            m.Text(
                second_column_name,
                font="Monospace",
                font_size=28,
                color=self.fontColor,
            )
            .move_to(self.camera.frame.get_center())
            .align_to(firstColumnTitle, m.UP)
        )
        thirdColumnTitle = (
            m.Text(
                third_column_name,
                font="Monospace",
                font_size=28,
                color=self.fontColor,
            )
            .move_to((vert2.get_center()[0] + 4, 0, 0))
            .align_to(firstColumnTitle, m.UP)
        )

        self.toFadeOut.add(
            horizontal,
            horizontal2,
            vert1,
            vert2,
            firstColumnTitle,
            secondColumnTitle,
            thirdColumnTitle,
        )

        if settings.animate:
            self.play(
                m.Create(horizontal),
                m.Create(horizontal2),
                m.Create(vert1),
                m.Create(vert2),
                m.AddTextLetterByLetter(firstColumnTitle),
                m.AddTextLetterByLetter(secondColumnTitle),
                m.AddTextLetterByLetter(thirdColumnTitle),
            )
        else:
            self.add(
                horizontal,
                horizontal2,
                vert1,
                vert2,
                firstColumnTitle,
                secondColumnTitle,
                thirdColumnTitle,
            )

        firstColumnFileNames = set()
        secondColumnFileNames = set()
        thirdColumnFileNames = set()

        firstColumnArrowMap = {}
        secondColumnArrowMap = {}
        thirdColumnArrowMap = {}

        self.populate_zones(
            firstColumnFileNames,
            secondColumnFileNames,
            thirdColumnFileNames,
            firstColumnArrowMap,
            secondColumnArrowMap,
            thirdColumnArrowMap,
        )

        firstColumnFiles = m.VGroup()
        secondColumnFiles = m.VGroup()
        thirdColumnFiles = m.VGroup()

        firstColumnFilesDict = {}
        secondColumnFilesDict = {}
        thirdColumnFilesDict = {}

        self.create_zone_text(
            firstColumnFileNames,
            secondColumnFileNames,
            thirdColumnFileNames,
            firstColumnFiles,
            secondColumnFiles,
            thirdColumnFiles,
            firstColumnFilesDict,
            secondColumnFilesDict,
            thirdColumnFilesDict,
            firstColumnTitle,
            secondColumnTitle,
            thirdColumnTitle,
            horizontal2,
        )

        if len(firstColumnFiles):
            if settings.animate:
                self.play(*[m.AddTextLetterByLetter(d) for d in firstColumnFiles])
            else:
                self.add(*[d for d in firstColumnFiles])

        if len(secondColumnFiles):
            if settings.animate:
                self.play(*[m.AddTextLetterByLetter(w) for w in secondColumnFiles])
            else:
                self.add(*[w for w in secondColumnFiles])

        if len(thirdColumnFiles):
            if settings.animate:
                self.play(*[m.AddTextLetterByLetter(s) for s in thirdColumnFiles])
            else:
                self.add(*[s for s in thirdColumnFiles])

        for filename in firstColumnArrowMap:
            if reverse:
                firstColumnArrowMap[filename].put_start_and_end_on(
                    (
                        firstColumnFilesDict[filename].get_right()[0] + 0.25,
                        firstColumnFilesDict[filename].get_right()[1],
                        0,
                    ),
                    (
                        secondColumnFilesDict[filename].get_left()[0] - 0.25,
                        secondColumnFilesDict[filename].get_left()[1],
                        0,
                    ),
                )
            else:
                firstColumnArrowMap[filename].put_start_and_end_on(
                    (
                        firstColumnFilesDict[filename].get_right()[0] + 0.25,
                        firstColumnFilesDict[filename].get_right()[1],
                        0,
                    ),
                    (
                        thirdColumnFilesDict[filename].get_left()[0] - 0.25,
                        thirdColumnFilesDict[filename].get_left()[1],
                        0,
                    ),
                )
            if settings.animate:
                self.play(m.Create(firstColumnArrowMap[filename]))
            else:
                self.add(firstColumnArrowMap[filename])
            self.toFadeOut.add(firstColumnArrowMap[filename])

        for filename in secondColumnArrowMap:
            secondColumnArrowMap[filename].put_start_and_end_on(
                (
                    secondColumnFilesDict[filename].get_right()[0] + 0.25,
                    secondColumnFilesDict[filename].get_right()[1],
                    0,
                ),
                (
                    thirdColumnFilesDict[filename].get_left()[0] - 0.25,
                    thirdColumnFilesDict[filename].get_left()[1],
                    0,
                ),
            )
            if settings.animate:
                self.play(m.Create(secondColumnArrowMap[filename]))
            else:
                self.add(secondColumnArrowMap[filename])
            self.toFadeOut.add(secondColumnArrowMap[filename])

        for filename in thirdColumnArrowMap:
            thirdColumnArrowMap[filename].put_start_and_end_on(
                (
                    thirdColumnFilesDict[filename].get_left()[0] - 0.25,
                    thirdColumnFilesDict[filename].get_left()[1],
                    0,
                ),
                (
                    firstColumnFilesDict[filename].get_right()[0] + 0.25,
                    firstColumnFilesDict[filename].get_right()[1],
                    0,
                ),
            )

            if settings.animate:
                self.play(m.Create(thirdColumnArrowMap[filename]))
            else:
                self.add(thirdColumnArrowMap[filename])
            self.toFadeOut.add(thirdColumnArrowMap[filename])

        self.toFadeOut.add(firstColumnFiles, secondColumnFiles, thirdColumnFiles)

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        for x in self.repo.index.diff(None):
            if "git-sim_media" not in x.a_path:
                secondColumnFileNames.add(x.a_path)

        try:
            for y in self.repo.index.diff("HEAD"):
                if "git-sim_media" not in y.a_path:
                    thirdColumnFileNames.add(y.a_path)
        except git.exc.BadName:
            for (y, _stage), entry in self.repo.index.entries.items():
                if "git-sim_media" not in y:
                    thirdColumnFileNames.add(y)

        for z in self.repo.untracked_files:
            if "git-sim_media" not in z:
                firstColumnFileNames.add(z)

    def center_frame_on_commit(self, commit):
        if settings.animate:
            self.play(
                self.camera.frame.animate.move_to(
                    self.drawnCommits[commit.hexsha].get_center()
                )
            )
        else:
            self.camera.frame.move_to(self.drawnCommits[commit.hexsha].get_center())

    def reset_head_branch(self, hexsha, shift=numpy.array([0.0, 0.0, 0.0])):
        if settings.animate:
            self.play(
                self.drawnRefs["HEAD"].animate.move_to(
                    (
                        self.drawnCommits[hexsha].get_center()[0] + shift[0],
                        self.drawnCommits[hexsha].get_center()[1] + 1.4 + shift[1],
                        0,
                    )
                ),
                self.drawnRefs[self.repo.active_branch.name].animate.move_to(
                    (
                        self.drawnCommits[hexsha].get_center()[0] + shift[0],
                        self.drawnCommits[hexsha].get_center()[1] + 2 + shift[1],
                        0,
                    )
                ),
            )
        else:
            self.drawnRefs["HEAD"].move_to(
                (
                    self.drawnCommits[hexsha].get_center()[0] + shift[0],
                    self.drawnCommits[hexsha].get_center()[1] + 1.4 + shift[1],
                    0,
                )
            )
            self.drawnRefs[self.repo.active_branch.name].move_to(
                (
                    self.drawnCommits[hexsha].get_center()[0] + shift[0],
                    self.drawnCommits[hexsha].get_center()[1] + 2 + shift[1],
                    0,
                )
            )

    def reset_head_branch_to_ref(self, ref, shift=numpy.array([0.0, 0.0, 0.0])):
        if settings.animate:
            self.play(self.drawnRefs["HEAD"].animate.next_to(ref, m.UP))
            self.play(
                self.drawnRefs[self.repo.active_branch.name].animate.next_to(
                    self.drawnRefs["HEAD"], m.UP
                )
            )
        else:
            self.drawnRefs["HEAD"].next_to(ref, m.UP)
            self.drawnRefs[self.repo.active_branch.name].next_to(
                self.drawnRefs["HEAD"], m.UP
            )

    def translate_frame(self, shift):
        if settings.animate:
            self.play(self.camera.frame.animate.shift(shift))
        else:
            self.camera.frame.shift(shift)

    def setup_and_draw_parent(
        self,
        child,
        commitMessage="New commit",
        shift=numpy.array([0.0, 0.0, 0.0]),
        draw_arrow=True,
        color=m.RED,
    ):
        circle = m.Circle(stroke_color=color, fill_color=color, fill_opacity=0.25)
        circle.height = 1
        circle.next_to(
            self.drawnCommits[child.hexsha],
            m.LEFT if settings.reverse else m.RIGHT,
            buff=1.5,
        )
        circle.shift(shift)

        start = circle.get_center()
        end = self.drawnCommits[child.hexsha].get_center()
        arrow = m.Arrow(start, end, color=self.fontColor)
        length = numpy.linalg.norm(start - end) - (1.5 if start[1] == end[1] else 3)
        arrow.set_length(length)

        commitId = m.Text(
            "abcdef", font="Monospace", font_size=20, color=self.fontColor
        ).next_to(circle, m.UP)
        self.toFadeOut.add(commitId)

        commitMessage = commitMessage.split("\n")[0][:40].replace("\n", " ")
        message = m.Text(
            "\n".join(
                commitMessage[j : j + 20] for j in range(0, len(commitMessage), 20)
            )[:100],
            font="Monospace",
            font_size=14,
            color=self.fontColor,
        ).next_to(circle, m.DOWN)
        self.toFadeOut.add(message)

        if settings.animate:
            self.play(
                self.camera.frame.animate.move_to(circle.get_center()),
                m.Create(circle),
                m.AddTextLetterByLetter(commitId),
                m.AddTextLetterByLetter(message),
                run_time=1 / settings.speed,
            )
        else:
            self.camera.frame.move_to(circle.get_center())
            self.add(circle, commitId, message)

        self.drawnCommits["abcdef"] = circle
        self.toFadeOut.add(circle)

        if draw_arrow:
            if settings.animate:
                self.play(m.Create(arrow), run_time=1 / settings.speed)
            else:
                self.add(arrow)
            self.toFadeOut.add(arrow)

        return commitId

    def draw_arrow_between_commits(self, startsha, endsha):
        start = self.drawnCommits[startsha].get_center()
        end = self.drawnCommits[endsha].get_center()

        arrow = DottedLine(
            start, end, color=self.fontColor, dot_kwargs={"color": self.fontColor}
        ).add_tip()
        length = numpy.linalg.norm(start - end) - 1.65
        arrow.set_length(length)
        self.draw_arrow(True, arrow)

    def create_dark_commit(self):
        return "dark"

    def get_nondark_commits(self):
        nondark_commits = []
        return nondark_commits

    def draw_ref(self, commit, top, i=0, text="HEAD", color=m.BLUE):
        refText = m.Text(text, font="Monospace", font_size=20, color=self.fontColor)
        refbox = m.Rectangle(
            color=color,
            fill_color=color,
            fill_opacity=0.25,
            height=0.4,
            width=refText.width + 0.25,
        )
        refbox.next_to(top, m.UP)
        refText.move_to(refbox.get_center())

        ref = m.VGroup(refbox, refText)

        if settings.animate:
            self.play(m.Create(ref), run_time=1 / settings.speed)
        else:
            self.add(ref)

        self.toFadeOut.add(ref)
        self.drawnRefs[text] = ref
        self.prevRef = ref

        if i == 0 and self.first_parse:
            self.topref = self.prevRef

    def draw_dark_ref(self):
        refRec = m.Rectangle(
            color=m.WHITE if settings.light_mode else m.BLACK,
            fill_color=m.WHITE if settings.light_mode else m.BLACK,
            height=0.4,
            width=1,
        )
        refRec.next_to(self.prevRef, m.UP)
        self.add(refRec)
        self.toFadeOut.add(refRec)
        self.prevRef = refRec

    def trim_path(self, path):
        return (path[:15] + "..." + path[-15:]) if len(path) > 30 else path

    def get_remote_tracking_branches(self):
        remote_refs = [remote.refs for remote in self.repo.remotes]
        remote_tracking_branches = {}
        for reflist in remote_refs:
            for ref in reflist:
                if "HEAD" not in ref.name and ref.name not in remote_tracking_branches:
                    remote_tracking_branches[ref.name] = ref.commit.hexsha
        return remote_tracking_branches

    def is_remote_tracking_branch(self, branch):
        remote_refs = [remote.refs for remote in self.repo.remotes]
        remote_tracking_branches = {}
        for reflist in remote_refs:
            for ref in reflist:
                if "HEAD" not in ref.name and ref.name not in remote_tracking_branches:
                    remote_tracking_branches[ref.name] = ref.commit.hexsha
        return branch in remote_tracking_branches

    def create_zone_text(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnFiles,
        secondColumnFiles,
        thirdColumnFiles,
        firstColumnFilesDict,
        secondColumnFilesDict,
        thirdColumnFilesDict,
        firstColumnTitle,
        secondColumnTitle,
        thirdColumnTitle,
        horizontal2,
    ):

        for i, f in enumerate(firstColumnFileNames):
            text = (
                m.Text(
                    self.trim_path(f),
                    font="Monospace",
                    font_size=24,
                    color=self.fontColor,
                )
                .move_to(
                    (firstColumnTitle.get_center()[0], horizontal2.get_center()[1], 0)
                )
                .shift(m.DOWN * 0.5 * (i + 1))
            )
            firstColumnFiles.add(text)
            firstColumnFilesDict[f] = text

        for j, f in enumerate(secondColumnFileNames):
            text = (
                m.Text(
                    self.trim_path(f),
                    font="Monospace",
                    font_size=24,
                    color=self.fontColor,
                )
                .move_to(
                    (secondColumnTitle.get_center()[0], horizontal2.get_center()[1], 0)
                )
                .shift(m.DOWN * 0.5 * (j + 1))
            )
            secondColumnFiles.add(text)
            secondColumnFilesDict[f] = text

        for h, f in enumerate(thirdColumnFileNames):
            text = (
                m.Text(
                    self.trim_path(f),
                    font="Monospace",
                    font_size=24,
                    color=self.fontColor,
                )
                .move_to(
                    (thirdColumnTitle.get_center()[0], horizontal2.get_center()[1], 0)
                )
                .shift(m.DOWN * 0.5 * (h + 1))
            )
            thirdColumnFiles.add(text)
            thirdColumnFilesDict[f] = text


class DottedLine(m.Line):
    def __init__(self, *args, dot_spacing=0.4, dot_kwargs={}, **kwargs):
        m.Line.__init__(self, *args, **kwargs)
        n_dots = int(self.get_length() / dot_spacing) + 1
        dot_spacing = self.get_length() / (n_dots - 1)
        unit_vector = self.get_unit_vector()
        start = self.start

        self.dot_points = [start + unit_vector * dot_spacing * x for x in range(n_dots)]
        self.dots = [m.Dot(point, **dot_kwargs) for point in self.dot_points]

        self.clear_points()

        self.add(*self.dots)

        self.get_start = lambda: self.dot_points[0]
        self.get_end = lambda: self.dot_points[-1]

    def get_first_handle(self):
        return self.dot_points[-1]

    def get_last_handle(self):
        return self.dot_points[-2]
