import platform
import sys

import git
import manim as m
import numpy


class GitSimBaseCommand:
    def __init__(self, scene):
        self.scene = scene
        self.init_repo()

        self.drawnCommits = {}
        self.drawnRefs = {}
        self.drawnCommitIds = {}
        self.commits = []
        self.zoomOuts = 0
        self.toFadeOut = m.Group()
        self.trimmed = False
        self.prevRef = None
        self.topref = None
        self.maxrefs = None
        self.i = 0
        self.numCommits = 5
        self.defaultNumCommits = 5
        self.selected_branches = []
        self.hide_first_tag = False
        self.stop = False
        self.zone_title_offset = 2.6 if platform.system() == "Windows" else 2.6
        self.allow_no_commits = False

        self.logo = m.ImageMobject(self.scene.args.logo)
        self.logo.width = 3

    def init_repo(self):
        try:
            self.repo = git.Repo(search_parent_directories=True)
        except git.exc.InvalidGitRepositoryError:
            print("git-sim error: No Git repository found at current path.")
            sys.exit(1)

    def execute(self):
        print("Simulating: git " + self.scene.args.subcommand)
        self.show_intro()
        self.get_commits()
        self.fadeout()
        self.show_outro()

    def get_commits(self, start="HEAD"):
        if not self.numCommits:
            if self.allow_no_commits:
                self.numCommits = self.defaultNumCommits
                self.commits = ["dark"] * 5
                self.zone_title_offset = 2
                return
            else:
                print("git-sim error: No commits in current Git repository.")
                sys.exit(1)

        try:
            self.commits = (
                list(self.repo.iter_commits(start))
                if self.numCommits == 1
                else list(
                    self.repo.iter_commits(
                        start + "~" + str(self.numCommits) + "..." + start
                    )
                )
            )
            if len(self.commits) < self.defaultNumCommits:
                self.commits = list(self.repo.iter_commits(start))
            while len(self.commits) < self.defaultNumCommits:
                self.commits.append(self.create_dark_commit())
            self.numCommits = self.defaultNumCommits

        except git.exc.GitCommandError:
            self.numCommits -= 1
            self.get_commits(start=start)

    def parse_commits(
        self, commit, prevCircle=None, shift=numpy.array([0.0, 0.0, 0.0]), dots=False
    ):
        if self.stop:
            return
        if self.i < self.numCommits and commit in self.commits:
            commitId, circle, arrow, hide_refs = self.draw_commit(
                commit, prevCircle, shift, dots
            )

            if commit != "dark":
                if not hide_refs and not self.stop:
                    self.draw_head(commit, commitId)
                    self.draw_branch(commit)
                    self.draw_tag(commit)
                self.draw_arrow(prevCircle, arrow)
                if self.stop:
                    return
                if self.i == 0 and len(self.drawnRefs) < 2:
                    self.draw_dark_ref()

            if self.i < len(self.commits) - 1:
                self.i += 1
                self.parse_commits(self.commits[self.i], circle, dots=True)
            else:
                self.i = 0

    def show_intro(self):
        if self.scene.args.animate and self.scene.args.show_intro:
            self.scene.add(self.logo)

            initialCommitText = m.Text(
                self.scene.args.title,
                font="Monospace",
                font_size=36,
                color=self.scene.fontColor,
            ).to_edge(m.UP, buff=1)
            self.scene.add(initialCommitText)
            self.scene.wait(2)
            self.scene.play(m.FadeOut(initialCommitText))
            self.scene.play(
                self.logo.animate.scale(0.25)
                .to_edge(m.UP, buff=0)
                .to_edge(m.RIGHT, buff=0)
            )

            self.scene.camera.frame.save_state()
            self.scene.play(m.FadeOut(self.logo))

        else:
            self.logo.scale(0.25).to_edge(m.UP, buff=0).to_edge(m.RIGHT, buff=0)
            self.scene.camera.frame.save_state()

    def show_outro(self):
        if self.scene.args.animate and self.scene.args.show_outro:

            self.scene.play(m.Restore(self.scene.camera.frame))

            self.scene.play(self.logo.animate.scale(4).set_x(0).set_y(0))

            outroTopText = m.Text(
                self.scene.args.outro_top_text,
                font="Monospace",
                font_size=36,
                color=self.scene.fontColor,
            ).to_edge(m.UP, buff=1)
            self.scene.play(m.AddTextLetterByLetter(outroTopText))

            outroBottomText = m.Text(
                self.scene.args.outro_bottom_text,
                font="Monospace",
                font_size=36,
                color=self.scene.fontColor,
            ).to_edge(m.DOWN, buff=1)
            self.scene.play(m.AddTextLetterByLetter(outroBottomText))

            self.scene.wait(3)

    def fadeout(self):
        if self.scene.args.animate:
            self.scene.wait(3)
            self.scene.play(
                m.FadeOut(self.toFadeOut), run_time=1 / self.scene.args.speed
            )
        else:
            self.scene.wait(0.1)

    def get_centers(self):
        centers = []
        for commit in self.drawnCommits.values():
            centers.append(commit.get_center())
        return centers

    def draw_commit(
        self, commit, prevCircle, shift=numpy.array([0.0, 0.0, 0.0]), dots=False
    ):
        if commit == "dark":
            commitFill = m.WHITE if self.scene.args.light_mode else m.BLACK
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
                prevCircle, m.RIGHT if self.scene.args.reverse else m.LEFT, buff=1.5
            )

        start = (
            prevCircle.get_center()
            if prevCircle
            else (m.LEFT if self.scene.args.reverse else m.RIGHT)
        )
        end = circle.get_center()

        if commit == "dark":
            arrow = m.Arrow(
                start, end, color=m.WHITE if self.scene.args.light_mode else m.BLACK
            )
        elif commit.hexsha in self.drawnCommits:
            end = self.drawnCommits[commit.hexsha].get_center()
            arrow = m.Arrow(start, end, color=self.scene.fontColor)
            self.stop = True
        else:
            arrow = m.Arrow(start, end, color=self.scene.fontColor)

        length = numpy.linalg.norm(start - end) - (1.5 if start[1] == end[1] else 3)
        arrow.set_length(length)

        commitId, commitMessage, commit, hide_refs = self.build_commit_id_and_message(
            commit, dots
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
            color=self.scene.fontColor,
        ).next_to(circle, m.DOWN)

        if self.scene.args.animate and commit != "dark" and not self.stop:
            self.scene.play(
                self.scene.camera.frame.animate.move_to(circle.get_center()),
                m.Create(circle),
                m.AddTextLetterByLetter(commitId),
                m.AddTextLetterByLetter(message),
                run_time=1 / self.scene.args.speed,
            )
        elif not self.stop:
            self.scene.add(circle, commitId, message)
        else:
            return commitId, circle, arrow, hide_refs

        if commit != "dark":
            self.drawnCommits[commit.hexsha] = circle

        self.toFadeOut.add(circle, commitId, message)
        self.prevRef = commitId

        return commitId, circle, arrow, hide_refs

    def build_commit_id_and_message(self, commit, dots=False):
        hide_refs = False
        if commit == "dark":
            commitId = m.Text(
                "", font="Monospace", font_size=20, color=self.scene.fontColor
            )
            commitMessage = ""
        elif (
            dots
            and self.commits[-1] != "dark"
            and commit.hexsha == self.commits[-1].hexsha
        ):
            commitId = m.Text(
                "...", font="Monospace", font_size=20, color=self.scene.fontColor
            )
            commitMessage = "..."
        else:
            commitId = m.Text(
                commit.hexsha[0:6],
                font="Monospace",
                font_size=20,
                color=self.scene.fontColor,
            )
            commitMessage = commit.message.split("\n")[0][:40].replace("\n", " ")
        return commitId, commitMessage, commit, hide_refs

    def draw_head(self, commit, commitId):
        if commit.hexsha == self.repo.head.commit.hexsha:
            headbox = m.Rectangle(color=m.BLUE, fill_color=m.BLUE, fill_opacity=0.25)
            headbox.width = 1
            headbox.height = 0.4
            headbox.next_to(commitId, m.UP)
            headText = m.Text(
                "HEAD", font="Monospace", font_size=20, color=self.scene.fontColor
            ).move_to(headbox.get_center())

            head = m.VGroup(headbox, headText)

            if self.scene.args.animate:
                self.scene.play(m.Create(head), run_time=1 / self.scene.args.speed)
            else:
                self.scene.add(head)

            self.toFadeOut.add(head)
            self.drawnRefs["HEAD"] = head
            self.prevRef = head

            if self.i == 0:
                self.topref = self.prevRef

    def draw_branch(self, commit):
        x = 0

        remote_tracking_branches = self.get_remote_tracking_branches()

        branches = [branch.name for branch in self.repo.heads] + list(
            remote_tracking_branches.keys()
        )

        for selected_branch in self.selected_branches:
            branches.insert(0, branches.pop(branches.index(selected_branch)))

        for branch in branches:
            # Use forward slash to check if branch is local or remote tracking
            # and draw the branch label if its hexsha matches the current commit
            if (
                "/" not in branch  # local branch
                and commit.hexsha == self.repo.heads[branch].commit.hexsha
            ) or (
                "/" in branch  # remote tracking branch
                and commit.hexsha == remote_tracking_branches[branch]
            ):
                branchText = m.Text(
                    branch, font="Monospace", font_size=20, color=self.scene.fontColor
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

                if self.scene.args.animate:
                    self.scene.play(
                        m.Create(fullbranch), run_time=1 / self.scene.args.speed
                    )
                else:
                    self.scene.add(fullbranch)

                self.toFadeOut.add(branchRec, branchText)
                self.drawnRefs[branch] = fullbranch

                if self.i == 0:
                    self.topref = self.prevRef

                x += 1
                if x >= self.scene.args.max_branches_per_commit:
                    return

    def draw_tag(self, commit):
        x = 0

        if self.hide_first_tag and self.i == 0:
            return

        for tag in self.repo.tags:

            try:
                if commit.hexsha == tag.commit.hexsha:
                    tagText = m.Text(
                        tag.name,
                        font="Monospace",
                        font_size=20,
                        color=self.scene.fontColor,
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

                    if self.scene.args.animate:
                        self.scene.play(
                            m.Create(tagRec),
                            m.Create(tagText),
                            run_time=1 / self.scene.args.speed,
                        )
                    else:
                        self.scene.add(tagRec, tagText)

                    self.toFadeOut.add(tagRec, tagText)

                    if self.i == 0:
                        self.topref = self.prevRef

                    x += 1
                    if x >= self.scene.args.max_tags_per_commit:
                        return
            except ValueError:
                pass

    def draw_arrow(self, prevCircle, arrow):
        if prevCircle:
            if self.scene.args.animate:
                self.scene.play(m.Create(arrow), run_time=1 / self.scene.args.speed)
            else:
                self.scene.add(arrow)

            self.toFadeOut.add(arrow)

    def recenter_frame(self):
        if self.scene.args.animate:
            self.scene.play(
                self.scene.camera.frame.animate.move_to(self.toFadeOut.get_center()),
                run_time=1 / self.scene.args.speed,
            )
        else:
            self.scene.camera.frame.move_to(self.toFadeOut.get_center())

    def scale_frame(self):
        if self.scene.args.animate:
            self.scene.play(
                self.scene.camera.frame.animate.scale_to_fit_width(
                    self.toFadeOut.get_width() * 1.1
                ),
                run_time=1 / self.scene.args.speed,
            )
            if self.toFadeOut.get_height() >= self.scene.camera.frame.get_height():
                self.scene.play(
                    self.scene.camera.frame.animate.scale_to_fit_height(
                        self.toFadeOut.get_height() * 1.25
                    ),
                    run_time=1 / self.scene.args.speed,
                )
        else:
            self.scene.camera.frame.scale_to_fit_width(self.toFadeOut.get_width() * 1.1)
            if self.toFadeOut.get_height() >= self.scene.camera.frame.get_height():
                self.scene.camera.frame.scale_to_fit_height(
                    self.toFadeOut.get_height() * 1.25
                )

    def vsplit_frame(self):
        if self.scene.args.animate:
            self.scene.play(
                self.scene.camera.frame.animate.scale_to_fit_height(
                    self.scene.camera.frame.get_height() * 2
                )
            )
        else:
            self.scene.camera.frame.scale_to_fit_height(
                self.scene.camera.frame.get_height() * 2
            )

        try:
            if self.scene.args.animate:
                self.scene.play(
                    self.toFadeOut.animate.align_to(
                        self.scene.camera.frame, m.UP
                    ).shift(m.DOWN * 0.75)
                )
            else:
                self.toFadeOut.align_to(self.scene.camera.frame, m.UP).shift(
                    m.DOWN * 0.75
                )
        except ValueError:
            pass

    def setup_and_draw_zones(
        self,
        first_column_name="Untracked files",
        second_column_name="Working directory modifications",
        third_column_name="Staging area",
        reverse=False,
    ):
        horizontal = m.Line(
            (
                self.scene.camera.frame.get_left()[0],
                self.scene.camera.frame.get_center()[1],
                0,
            ),
            (
                self.scene.camera.frame.get_right()[0],
                self.scene.camera.frame.get_center()[1],
                0,
            ),
            color=self.scene.fontColor,
        ).shift(m.UP * 2.5)
        horizontal2 = m.Line(
            (
                self.scene.camera.frame.get_left()[0],
                self.scene.camera.frame.get_center()[1],
                0,
            ),
            (
                self.scene.camera.frame.get_right()[0],
                self.scene.camera.frame.get_center()[1],
                0,
            ),
            color=self.scene.fontColor,
        ).shift(m.UP * 1.5)
        vert1 = m.DashedLine(
            (
                self.scene.camera.frame.get_left()[0],
                self.scene.camera.frame.get_bottom()[1],
                0,
            ),
            (self.scene.camera.frame.get_left()[0], horizontal.get_start()[1], 0),
            dash_length=0.2,
            color=self.scene.fontColor,
        ).shift(m.RIGHT * 6.5)
        vert2 = m.DashedLine(
            (
                self.scene.camera.frame.get_right()[0],
                self.scene.camera.frame.get_bottom()[1],
                0,
            ),
            (self.scene.camera.frame.get_right()[0], horizontal.get_start()[1], 0),
            dash_length=0.2,
            color=self.scene.fontColor,
        ).shift(m.LEFT * 6.5)

        if reverse:
            first_column_name = "Staging area"
            third_column_name = "Deleted changes"

        firstColumnTitle = (
            m.Text(
                first_column_name,
                font="Monospace",
                font_size=28,
                color=self.scene.fontColor,
            )
            .align_to(self.scene.camera.frame, m.LEFT)
            .shift(m.RIGHT * 0.65)
            .shift(m.UP * self.zone_title_offset)
        )
        secondColumnTitle = (
            m.Text(
                second_column_name,
                font="Monospace",
                font_size=28,
                color=self.scene.fontColor,
            )
            .move_to(self.scene.camera.frame.get_center())
            .align_to(firstColumnTitle, m.UP)
        )
        thirdColumnTitle = (
            m.Text(
                third_column_name,
                font="Monospace",
                font_size=28,
                color=self.scene.fontColor,
            )
            .align_to(self.scene.camera.frame, m.RIGHT)
            .shift(m.LEFT * 1.65)
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

        if self.scene.args.animate:
            self.scene.play(
                m.Create(horizontal),
                m.Create(horizontal2),
                m.Create(vert1),
                m.Create(vert2),
                m.AddTextLetterByLetter(firstColumnTitle),
                m.AddTextLetterByLetter(secondColumnTitle),
                m.AddTextLetterByLetter(thirdColumnTitle),
            )
        else:
            self.scene.add(
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

        self.populate_zones(
            firstColumnFileNames,
            secondColumnFileNames,
            thirdColumnFileNames,
            firstColumnArrowMap,
            secondColumnArrowMap,
        )

        firstColumnFiles = m.VGroup()
        secondColumnFiles = m.VGroup()
        thirdColumnFiles = m.VGroup()

        firstColumnFilesDict = {}
        secondColumnFilesDict = {}
        thirdColumnFilesDict = {}

        for i, f in enumerate(firstColumnFileNames):
            text = (
                m.Text(
                    self.trim_path(f),
                    font="Monospace",
                    font_size=24,
                    color=self.scene.fontColor,
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
                    color=self.scene.fontColor,
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
                    color=self.scene.fontColor,
                )
                .move_to(
                    (thirdColumnTitle.get_center()[0], horizontal2.get_center()[1], 0)
                )
                .shift(m.DOWN * 0.5 * (h + 1))
            )
            thirdColumnFiles.add(text)
            thirdColumnFilesDict[f] = text

        if len(firstColumnFiles):
            if self.scene.args.animate:
                self.scene.play(*[m.AddTextLetterByLetter(d) for d in firstColumnFiles])
            else:
                self.scene.add(*[d for d in firstColumnFiles])

        if len(secondColumnFiles):
            if self.scene.args.animate:
                self.scene.play(
                    *[m.AddTextLetterByLetter(w) for w in secondColumnFiles]
                )
            else:
                self.scene.add(*[w for w in secondColumnFiles])

        if len(thirdColumnFiles):
            if self.scene.args.animate:
                self.scene.play(*[m.AddTextLetterByLetter(s) for s in thirdColumnFiles])
            else:
                self.scene.add(*[s for s in thirdColumnFiles])

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
            if self.scene.args.animate:
                self.scene.play(m.Create(firstColumnArrowMap[filename]))
            else:
                self.scene.add(firstColumnArrowMap[filename])
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
            if self.scene.args.animate:
                self.scene.play(m.Create(secondColumnArrowMap[filename]))
            else:
                self.scene.add(secondColumnArrowMap[filename])
            self.toFadeOut.add(secondColumnArrowMap[filename])

        self.toFadeOut.add(firstColumnFiles, secondColumnFiles, thirdColumnFiles)

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
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
        if self.scene.args.animate:
            self.scene.play(
                self.scene.camera.frame.animate.move_to(
                    self.drawnCommits[commit.hexsha].get_center()
                )
            )
        else:
            self.scene.camera.frame.move_to(
                self.drawnCommits[commit.hexsha].get_center()
            )

    def reset_head_branch(self, hexsha, shift=numpy.array([0.0, 0.0, 0.0])):
        if self.scene.args.animate:
            self.scene.play(
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

    def translate_frame(self, shift):
        if self.scene.args.animate:
            self.scene.play(self.scene.camera.frame.animate.shift(shift))
        else:
            self.scene.camera.frame.shift(shift)

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
            m.LEFT if self.scene.args.reverse else m.RIGHT,
            buff=1.5,
        )
        circle.shift(shift)

        start = circle.get_center()
        end = self.drawnCommits[child.hexsha].get_center()
        arrow = m.Arrow(start, end, color=self.scene.fontColor)
        length = numpy.linalg.norm(start - end) - (1.5 if start[1] == end[1] else 3)
        arrow.set_length(length)

        commitId = m.Text(
            "abcdef", font="Monospace", font_size=20, color=self.scene.fontColor
        ).next_to(circle, m.UP)
        self.toFadeOut.add(commitId)

        commitMessage = commitMessage.split("\n")[0][:40].replace("\n", " ")
        message = m.Text(
            "\n".join(
                commitMessage[j : j + 20] for j in range(0, len(commitMessage), 20)
            )[:100],
            font="Monospace",
            font_size=14,
            color=self.scene.fontColor,
        ).next_to(circle, m.DOWN)
        self.toFadeOut.add(message)

        if self.scene.args.animate:
            self.scene.play(
                self.scene.camera.frame.animate.move_to(circle.get_center()),
                m.Create(circle),
                m.AddTextLetterByLetter(commitId),
                m.AddTextLetterByLetter(message),
                run_time=1 / self.scene.args.speed,
            )
        else:
            self.scene.camera.frame.move_to(circle.get_center())
            self.scene.add(circle, commitId, message)

        self.drawnCommits["abcdef"] = circle
        self.toFadeOut.add(circle)

        if draw_arrow:
            if self.scene.args.animate:
                self.scene.play(m.Create(arrow), run_time=1 / self.scene.args.speed)
            else:
                self.scene.add(arrow)
            self.toFadeOut.add(arrow)

        return commitId

    def draw_arrow_between_commits(self, startsha, endsha):
        start = self.drawnCommits[startsha].get_center()
        end = self.drawnCommits[endsha].get_center()

        arrow = DottedLine(start, end, color=self.scene.fontColor).add_tip()
        length = numpy.linalg.norm(start - end) - 1.65
        arrow.set_length(length)
        self.draw_arrow(True, arrow)

    def create_dark_commit(self):
        return "dark"

    def get_nondark_commits(self):
        nondark_commits = []
        for commit in self.commits:
            if commit != "dark":
                nondark_commits.append(commit)
        return nondark_commits

    def draw_ref(self, commit, top, text="HEAD", color=m.BLUE):
        refText = m.Text(
            text, font="Monospace", font_size=20, color=self.scene.fontColor
        )
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

        if self.scene.args.animate:
            self.scene.play(m.Create(ref), run_time=1 / self.scene.args.speed)
        else:
            self.scene.add(ref)

        self.toFadeOut.add(ref)
        self.drawnRefs[text] = ref
        self.prevRef = ref

        if self.i == 0:
            self.topref = self.prevRef

    def draw_dark_ref(self):
        refRec = m.Rectangle(
            color=m.WHITE if self.scene.args.light_mode else m.BLACK,
            fill_color=m.WHITE if self.scene.args.light_mode else m.BLACK,
            height=0.4,
            width=1,
        )
        refRec.next_to(self.prevRef, m.UP)
        self.scene.add(refRec)
        self.toFadeOut.add(refRec)
        self.prevRef = refRec

    def trim_path(self, path):
        return (path[:5] + "..." + path[-15:]) if len(path) > 20 else path

    def get_remote_tracking_branches(self):
        remote_refs = [remote.refs for remote in self.repo.remotes]
        remote_tracking_branches = {}
        for reflist in remote_refs:
            for ref in reflist:
                if "HEAD" not in ref.name and ref.name not in remote_tracking_branches:
                    remote_tracking_branches[ref.name] = ref.commit.hexsha
        return remote_tracking_branches


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
