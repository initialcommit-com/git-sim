from manim import *
import git, sys, numpy

class GitSim(MovingCameraScene):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.drawnCommits = {}
        self.drawnRefs = {}
        self.commits = []
        self.zoomOuts = 0
        self.toFadeOut = Group()

        if ( self.args.light_mode ):
            self.fontColor = BLACK
        else:
            self.fontColor = WHITE

    def construct(self):

        try:
            self.repo = git.Repo(search_parent_directories=True)
        except git.exc.InvalidGitRepositoryError:
            print("git-sim error: No Git repository found at current path.")
            sys.exit(1)

        logo = ImageMobject(self.args.logo)
        logo.width = 3

        if ( self.args.show_intro ):
            self.add(logo)

            initialCommitText = Text(self.args.title, font="Monospace", font_size=36, color=self.fontColor).to_edge(UP, buff=1)
            self.add(initialCommitText)
            self.wait(2)
            self.play(FadeOut(initialCommitText))
            self.play(logo.animate.scale(0.25).to_edge(UP, buff=0).to_edge(RIGHT, buff=0))
    
            self.camera.frame.save_state()
            self.play(FadeOut(logo))

        else:
            logo.scale(0.25).to_edge(UP, buff=0).to_edge(RIGHT, buff=0)
            self.camera.frame.save_state()

        if self.args.subcommand == 'reset':
            self.reset()

        self.wait(3)

        self.play(FadeOut(self.toFadeOut), run_time=1/self.args.speed)

        if ( self.args.show_outro ):

            self.play(Restore(self.camera.frame))

            self.play(logo.animate.scale(4).set_x(0).set_y(0))

            outroTopText = Text(self.args.outro_top_text, font="Monospace", font_size=36, color=self.fontColor).to_edge(UP, buff=1)
            self.play(AddTextLetterByLetter(outroTopText))

            outroBottomText = Text(self.args.outro_bottom_text, font="Monospace", font_size=36, color=self.fontColor).to_edge(DOWN, buff=1)
            self.play(AddTextLetterByLetter(outroBottomText))

            self.wait(3)

    def reset(self):
        print("Simulating: git reset" + ( " --" + self.args.mode if self.args.mode != "default" else "" ) + " " + self.args.commit)

        self.resetTo = git.repo.fun.rev_parse(self.repo, self.args.commit)

        try:
            self.trimmed = False
            self.commits = list(self.repo.iter_commits('HEAD~5...HEAD'))
            if self.resetTo not in self.commits:
                self.commits = list(self.repo.iter_commits(self.args.commit + '~3...HEAD'))

            resetToInd = self.commits.index(self.resetTo)
            self.commitsSinceResetTo = self.commits[:resetToInd]

            if len(self.commits) > 5:
                self.commits = self.commits[:3] + self.commits[resetToInd:resetToInd+2]
                self.trimmed = True

        except git.exc.GitCommandError:
            print("git-sim error: No commits in current Git repository.")
            sys.exit(1)

        commit = self.commits[0]

        i = 0 
        prevCircle = None

        self.parseCommits(commit, i, prevCircle, self.toFadeOut)

        self.play(self.camera.frame.animate.move_to(self.toFadeOut.get_center()), run_time=1/self.args.speed)
        self.play(self.camera.frame.animate.scale_to_fit_width(self.toFadeOut.get_width()*1.1), run_time=1/self.args.speed)

        if ( self.toFadeOut.get_height() >= self.camera.frame.get_height() ):
            self.play(self.camera.frame.animate.scale_to_fit_height(self.toFadeOut.get_height()*1.25), run_time=1/self.args.speed)

        self.play(self.drawnRefs["HEAD"].animate.move_to((self.drawnCommits[self.resetTo.hexsha].get_center()[0], self.drawnRefs["HEAD"].get_center()[1], 0)),
                  self.drawnRefs[self.repo.active_branch.name].animate.move_to((self.drawnCommits[self.resetTo.hexsha].get_center()[0], self.drawnRefs[self.repo.active_branch.name].get_center()[1], 0)))

        self.play(self.camera.frame.animate.scale_to_fit_height(self.camera.frame.get_height()*2))
        self.play(self.toFadeOut.animate.align_to(self.camera.frame, UP).shift(DOWN*0.75))

        horizontal = Line((self.camera.frame.get_left()[0], self.camera.frame.get_center()[1], 0), (self.camera.frame.get_right()[0], self.camera.frame.get_center()[1], 0), color=self.fontColor).shift(UP*2.5)
        horizontal2 = Line((self.camera.frame.get_left()[0], self.camera.frame.get_center()[1], 0), (self.camera.frame.get_right()[0], self.camera.frame.get_center()[1], 0), color=self.fontColor).shift(UP*1.5)
        vert1 = DashedLine((self.camera.frame.get_left()[0], self.camera.frame.get_bottom()[1], 0), (self.camera.frame.get_left()[0], horizontal.get_start()[1], 0), dash_length=0.2, color=self.fontColor).shift(RIGHT*6.5)
        vert2 = DashedLine((self.camera.frame.get_right()[0], self.camera.frame.get_bottom()[1], 0), (self.camera.frame.get_right()[0], horizontal.get_start()[1], 0), dash_length=0.2, color=self.fontColor).shift(LEFT*6.5)

        deletedText = Text("Changes deleted from", font="Monospace", font_size=28, color=self.fontColor).align_to(self.camera.frame, LEFT).shift(RIGHT*0.65).shift(UP*2.65)
        workingdirectoryText = Text("Working directory modifications", font="Monospace", font_size=28, color=self.fontColor).move_to(self.camera.frame.get_center()).align_to(deletedText, UP)
        stagingareaText = Text("Staged changes", font="Monospace", font_size=28, color=self.fontColor).align_to(self.camera.frame, RIGHT).shift(LEFT*1.65).align_to(deletedText, UP)

        self.toFadeOut.add(horizontal, horizontal2, vert1, vert2, deletedText, workingdirectoryText, stagingareaText)
        self.play(Create(horizontal), Create(horizontal2), Create(vert1), Create(vert2), AddTextLetterByLetter(deletedText), AddTextLetterByLetter(workingdirectoryText), AddTextLetterByLetter(stagingareaText))

        deletedFileNames = set()
        workingFileNames = set()
        stagedFileNames = set()

        for commit in self.commitsSinceResetTo:
            if commit.hexsha == self.resetTo.hexsha:
                break
            for filename in commit.stats.files:
                if self.args.mode == "soft":
                    stagedFileNames.add(filename)
                elif self.args.mode == "mixed" or self.args.mode == "default":
                    workingFileNames.add(filename)
                elif self.args.mode == "hard":
                    deletedFileNames.add(filename)

        for x in self.repo.index.diff(None):
            if self.args.mode == "soft":
                workingFileNames.add(x.a_path)
            elif self.args.mode == "mixed" or self.args.mode == "default":
                workingFileNames.add(x.a_path)
            elif self.args.mode == "hard":
                deletedFileNames.add(x.a_path)

        for y in self.repo.index.diff("HEAD"):
            if self.args.mode == "soft":
                stagedFileNames.add(y.a_path)
            elif self.args.mode == "mixed" or self.args.mode == "default":
                workingFileNames.add(y.a_path)
            elif self.args.mode == "hard":
                deletedFileNames.add(y.a_path)

        deletedFiles = VGroup()
        workingFiles = VGroup()
        stagedFiles = VGroup()

        for i, f in enumerate(deletedFileNames):
            deletedFiles.add(Text(f, font="Monospace", font_size=24, color=self.fontColor).move_to((deletedText.get_center()[0], horizontal2.get_center()[1], 0)).shift(DOWN*0.5*(i+1)))

        for j, f in enumerate(workingFileNames):
            workingFiles.add(Text(f, font="Monospace", font_size=24, color=self.fontColor).move_to((workingdirectoryText.get_center()[0], horizontal2.get_center()[1], 0)).shift(DOWN*0.5*(j+1)))

        for h, f in enumerate(stagedFileNames):
            stagedFiles.add(Text(f, font="Monospace", font_size=24, color=self.fontColor).move_to((stagingareaText.get_center()[0], horizontal2.get_center()[1], 0)).shift(DOWN*0.5*(h+1)))

        if len(deletedFiles):
            self.play(*[AddTextLetterByLetter(d) for d in deletedFiles])

        if len(workingFiles):
            self.play(*[AddTextLetterByLetter(w) for w in workingFiles])

        if len(stagedFiles):
            self.play(*[AddTextLetterByLetter(s) for s in stagedFiles])

        self.toFadeOut.add(deletedFiles, workingFiles, stagedFiles)

    def parseCommits(self, commit, i, prevCircle, toFadeOut):
        if ( i < self.args.commits and commit in self.commits ):

            if ( len(commit.parents) <= 1 ):
                commitFill = RED
            else:
                commitFill = GRAY

            circle = Circle(stroke_color=commitFill, fill_color=commitFill, fill_opacity=0.25)
            circle.height = 1

            if prevCircle:
                circle.next_to(prevCircle, RIGHT, buff=1.5)

            offset = 0
            while ( any((circle.get_center() == c).all() for c in self.getCenters()) ):
                circle.next_to(circle, DOWN, buff=3.5)
                offset += 1
                if ( self.zoomOuts == 0 ):
                    self.play(self.camera.frame.animate.scale(1.5), run_time=1/self.args.speed)
                self.zoomOuts += 1

            isNewCommit = commit.hexsha not in self.drawnCommits

            if ( isNewCommit ):
                start = prevCircle.get_center() if prevCircle else LEFT
                end = circle.get_center()
            else:
                start = prevCircle.get_center()
                end = self.drawnCommits[commit.hexsha].get_center()

            arrow = Arrow(start, end, color=self.fontColor)
            length = numpy.linalg.norm(start-end) - ( 1.5 if start[1] == end[1] else 3  )
            arrow.set_length(length)

            angle = arrow.get_angle()
            lineRect = Rectangle(height=0.1, width=length, color="#123456").move_to(arrow.get_center()).rotate(angle)

            for commitCircle in self.drawnCommits.values():
                inter = Intersection(lineRect, commitCircle)
                if ( inter.has_points() ):
                    arrow = CurvedArrow(start, end)
                    if ( start[1] == end[1]  ):
                        arrow.shift(UP*1.25)
                    if ( start[0] < end[0] and start[1] == end[1] ):
                        arrow.flip(RIGHT).shift(UP)

            if i == 2 and self.trimmed:
                commitId = Text('...', font="Monospace", font_size=20, color=self.fontColor).next_to(circle, UP)
                commitMessage = '...'
            else:
                commitId = Text(commit.hexsha[0:6], font="Monospace", font_size=20, color=self.fontColor).next_to(circle, UP)
                commitMessage = commit.message[:40].replace("\n", " ")

            message = Text('\n'.join(commitMessage[j:j+20] for j in range(0, len(commitMessage), 20))[:100], font="Monospace", font_size=14, color=self.fontColor).next_to(circle, DOWN)

            if ( isNewCommit ):

                self.play(self.camera.frame.animate.move_to(circle.get_center()), Create(circle), AddTextLetterByLetter(commitId), AddTextLetterByLetter(message), run_time=1/self.args.speed)
                self.drawnCommits[commit.hexsha] = circle

                prevRef = commitId
                if ( commit.hexsha == self.repo.head.commit.hexsha ):
                    headbox = Rectangle(color=BLUE, fill_color=BLUE, fill_opacity=0.25)
                    headbox.width = 1
                    headbox.height = 0.4
                    headbox.next_to(commitId, UP)
                    headText = Text("HEAD", font="Monospace", font_size=20, color=self.fontColor).move_to(headbox.get_center())

                    head = VGroup(headbox, headText)

                    self.play(Create(head), run_time=1/self.args.speed)
                    toFadeOut.add(head)
                    self.drawnRefs["HEAD"] = head
                    prevRef = head

                x = 0
                for branch in self.repo.heads:
                    if ( commit.hexsha == branch.commit.hexsha and branch.name == self.repo.active_branch.name ):
                        branchText = Text(branch.name, font="Monospace", font_size=20, color=self.fontColor)
                        branchRec = Rectangle(color=GREEN, fill_color=GREEN, fill_opacity=0.25, height=0.4, width=branchText.width+0.25)

                        branchRec.next_to(prevRef, UP)
                        branchText.move_to(branchRec.get_center())

                        fullbranch = VGroup(branchRec, branchText)

                        prevRef = fullbranch

                        self.play(Create(fullbranch), run_time=1/self.args.speed)
                        toFadeOut.add(branchRec, branchText)
                        self.drawnRefs[branch.name] = fullbranch

                        x += 1
                        if ( x >= self.args.max_branches_per_commit ):
                            break

                x = 0
                for tag in self.repo.tags:
                    if ( commit.hexsha == tag.commit.hexsha ):
                        tagText = Text(tag.name, font="Monospace", font_size=20, color=self.fontColor)
                        tagRec = Rectangle(color=YELLOW, fill_color=YELLOW, fill_opacity=0.25, height=0.4, width=tagText.width+0.25)

                        tagRec.next_to(prevRef, UP)
                        tagText.move_to(tagRec.get_center())

                        prevRef = tagRec

                        #self.play(Create(tagRec), Create(tagText), run_time=1/self.args.speed)
                        #toFadeOut.add(tagRec, tagText)

                        x += 1
                        if ( x >= self.args.max_tags_per_commit ):
                            break

            else:
                self.play(self.camera.frame.animate.move_to(self.drawnCommits[commit.hexsha].get_center()), run_time=1/self.args.speed)
                self.play(Create(arrow), run_time=1/self.args.speed)
                toFadeOut.add(arrow)
                return


            if ( prevCircle ):
                self.play(Create(arrow), run_time=1/self.args.speed)
                toFadeOut.add(arrow)

            prevCircle = circle

            toFadeOut.add(circle, commitId, message)

            if i < len(self.commits)-1:
                self.parseCommits(self.commits[i+1], i+1, prevCircle, toFadeOut)

        else:
            return

    def getCenters(self):
        centers = []
        for commit in self.drawnCommits.values():
            centers.append(commit.get_center())
        return centers
