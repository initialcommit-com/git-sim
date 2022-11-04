from manim import *
from git_sim_reset import *
from git_sim_branch import *
from git_sim_tag import *
import git, sys, numpy

class GitSim(MovingCameraScene):
    def __init__(self, args):
        super().__init__()
        self.args = args

        if ( self.args.light_mode ):
            self.fontColor = BLACK
        else:
            self.fontColor = WHITE

    def construct(self):

        if self.args.subcommand == 'branch':
            self.command = GitSimBranch(self)
        elif self.args.subcommand == 'tag':
            self.command = GitSimTag(self)
        elif self.args.subcommand == 'reset':
            self.command = GitSimReset(self)

        self.command.execute()

    def revert(self):
        print("Simulating: git revert " + self.args.commit)

        try:
            self.commits = list(self.repo.iter_commits('HEAD~4...HEAD'))

        except git.exc.GitCommandError:
            print("git-sim error: No commits in current Git repository.")
            sys.exit(1)

        revert = git.repo.fun.rev_parse(self.repo, self.args.commit)
        commit = self.commits[0]

        i = 0
        prevCircle = None

        self.parseCommits(commit, i, prevCircle, self.toFadeOut)

        self.play(self.camera.frame.animate.move_to(self.drawnCommits[self.commits[0].hexsha].get_center()))

        circle = Circle(stroke_color=RED, fill_color=RED, fill_opacity=0.25)
        circle.height = 1
        circle.next_to(self.drawnCommits[self.commits[0].hexsha], LEFT, buff=1.5)

        start = circle.get_center()
        end = self.drawnCommits[self.commits[0].hexsha].get_center()
        arrow = Arrow(start, end, color=self.fontColor)
        length = numpy.linalg.norm(start-end) - ( 1.5 if start[1] == end[1] else 3  )
        arrow.set_length(length)

        commitId = Text("abcdef", font="Monospace", font_size=20, color=self.fontColor).next_to(circle, UP)
        self.toFadeOut.add(commitId)

        commitMessage = "Revert " + revert.hexsha[0:6]
        commitMessage = commitMessage[:40].replace("\n", " ")
        message = Text('\n'.join(commitMessage[j:j+20] for j in range(0, len(commitMessage), 20))[:100], font="Monospace", font_size=14, color=self.fontColor).next_to(circle, DOWN)
        self.toFadeOut.add(message)

        self.play(self.camera.frame.animate.move_to(circle.get_center()), Create(circle), AddTextLetterByLetter(commitId), AddTextLetterByLetter(message), run_time=1/self.args.speed)
        self.drawnCommits[revert.hexsha] = circle
        self.toFadeOut.add(circle)

        self.play(Create(arrow), run_time=1/self.args.speed)
        self.toFadeOut.add(arrow)

        self.play(self.camera.frame.animate.move_to(self.toFadeOut.get_center()), run_time=1/self.args.speed)
        self.play(self.camera.frame.animate.scale_to_fit_width(self.toFadeOut.get_width()*1.1), run_time=1/self.args.speed)

        if ( self.toFadeOut.get_height() >= self.camera.frame.get_height() ):
            self.play(self.camera.frame.animate.scale_to_fit_height(self.toFadeOut.get_height()*1.25), run_time=1/self.args.speed)

        self.play(self.drawnRefs["HEAD"].animate.move_to((circle.get_center()[0], self.drawnRefs["HEAD"].get_center()[1], 0)),
                  self.drawnRefs[self.repo.active_branch.name].animate.move_to((circle.get_center()[0], self.drawnRefs[self.repo.active_branch.name].get_center()[1], 0)))

        self.play(self.camera.frame.animate.scale_to_fit_height(self.camera.frame.get_height()*2))
        self.play(self.toFadeOut.animate.align_to(self.camera.frame, UP).shift(DOWN*0.75))

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

            if ((i == 2 and self.trimmed and self.args.subcommand == 'reset') or
                (i == 3 and self.args.subcommand == 'revert')):
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

                    if i == 0:
                        self.topref = prevRef

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

                        if i == 0:
                            self.topref = prevRef

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

                        if i == 0:
                            self.topref = prevRef

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
