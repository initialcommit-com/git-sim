from manim import *
import git, sys, numpy

class GitSimBaseCommand():

    def __init__(self, scene):
        self.scene = scene
        self.init_repo()

        self.drawnCommits = {}
        self.drawnRefs = {}
        self.commits = []
        self.zoomOuts = 0 
        self.toFadeOut = Group()
        self.trimmed = False
        self.prevRef = None
        self.topref = None

        self.logo = ImageMobject(self.scene.args.logo)
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

    def show_intro(self):
        if ( self.scene.args.show_intro ):
            self.scene.add(self.logo)

            initialCommitText = Text(self.scene.args.title, font="Monospace", font_size=36, color=self.scene.fontColor).to_edge(UP, buff=1)
            self.scene.add(initialCommitText)
            self.scene.wait(2)
            self.scene.play(FadeOut(initialCommitText))
            self.scene.play(self.logo.animate.scale(0.25).to_edge(UP, buff=0).to_edge(RIGHT, buff=0))
    
            self.scene.camera.frame.save_state()
            self.scene.play(FadeOut(self.logo))

        else:
            self.logo.scale(0.25).to_edge(UP, buff=0).to_edge(RIGHT, buff=0)
            self.scene.camera.frame.save_state()        

    def show_outro(self):
        if ( self.scene.args.show_outro ):

            self.scene.play(Restore(self.scene.camera.frame))

            self.scene.play(self.logo.animate.scale(4).set_x(0).set_y(0))

            outroTopText = Text(self.scene.args.outro_top_text, font="Monospace", font_size=36, color=self.scene.fontColor).to_edge(UP, buff=1)
            self.scene.play(AddTextLetterByLetter(outroTopText))

            outroBottomText = Text(self.scene.args.outro_bottom_text, font="Monospace", font_size=36, color=self.scene.fontColor).to_edge(DOWN, buff=1)
            self.scene.play(AddTextLetterByLetter(outroBottomText))

            self.scene.wait(3)

    def fadeout(self):
        self.scene.wait(3)
        self.scene.play(FadeOut(self.toFadeOut), run_time=1/self.scene.args.speed)

    def get_commits(self):
        try:
            self.commits = list(self.repo.iter_commits('HEAD~5...HEAD'))

        except git.exc.GitCommandError:
            print("git-sim error: No commits in current Git repository.")
            sys.exit(1)

    def get_centers(self):
        centers = []
        for commit in self.drawnCommits.values():
            centers.append(commit.get_center())
        return centers

    def draw_commit(self, commit, prevCircle):
        if ( len(commit.parents) <= 1 ):
            commitFill = RED 
        else:
            commitFill = GRAY

        circle = Circle(stroke_color=commitFill, fill_color=commitFill, fill_opacity=0.25)
        circle.height = 1 

        if prevCircle:
            circle.next_to(prevCircle, RIGHT, buff=1.5)

        start = prevCircle.get_center() if prevCircle else LEFT
        end = circle.get_center()

        arrow = Arrow(start, end, color=self.scene.fontColor)
        length = numpy.linalg.norm(start-end) - ( 1.5 if start[1] == end[1] else 3  )
        arrow.set_length(length)

        commitId = Text(commit.hexsha[0:6], font="Monospace", font_size=20, color=self.scene.fontColor).next_to(circle, UP) 
        commitMessage = commit.message[:40].replace("\n", " ")

        message = Text('\n'.join(commitMessage[j:j+20] for j in range(0, len(commitMessage), 20))[:100], font="Monospace", font_size=14, color=self.scene.fontColor).next_to(circle, DOWN)

        self.scene.play(self.scene.camera.frame.animate.move_to(circle.get_center()), Create(circle), AddTextLetterByLetter(commitId), AddTextLetterByLetter(message), run_time=1/self.scene.args.speed)
        self.drawnCommits[commit.hexsha] = circle

        self.toFadeOut.add(circle, commitId, message)
        self.prevRef = commitId

        return commitId, circle, arrow

    def draw_head(self, commit, commitId, i):
        if ( commit.hexsha == self.repo.head.commit.hexsha ):
            headbox = Rectangle(color=BLUE, fill_color=BLUE, fill_opacity=0.25)
            headbox.width = 1 
            headbox.height = 0.4 
            headbox.next_to(commitId, UP) 
            headText = Text("HEAD", font="Monospace", font_size=20, color=self.scene.fontColor).move_to(headbox.get_center())

            head = VGroup(headbox, headText)

            self.scene.play(Create(head), run_time=1/self.scene.args.speed)
            self.toFadeOut.add(head)
            self.drawnRefs["HEAD"] = head
            self.prevRef = head

            if i == 0:
                self.topref = self.prevRef

    def draw_branch(self, commit, i):
        x = 0 
        for branch in self.repo.heads:
            if ( commit.hexsha == branch.commit.hexsha and branch.name == self.repo.active_branch.name ):
                branchText = Text(branch.name, font="Monospace", font_size=20, color=self.scene.fontColor)
                branchRec = Rectangle(color=GREEN, fill_color=GREEN, fill_opacity=0.25, height=0.4, width=branchText.width+0.25)

                branchRec.next_to(self.prevRef, UP) 
                branchText.move_to(branchRec.get_center())

                fullbranch = VGroup(branchRec, branchText)

                self.prevRef = fullbranch

                self.scene.play(Create(fullbranch), run_time=1/self.scene.args.speed)
                self.toFadeOut.add(branchRec, branchText)
                self.drawnRefs[branch.name] = fullbranch

                x += 1

                if i == 0:
                    self.topref = self.prevRef

    def draw_tag(self, commit, i):
        x = 0 
        for tag in self.repo.tags:
            if ( commit.hexsha == tag.commit.hexsha ):
                tagText = Text(tag.name, font="Monospace", font_size=20, color=self.scene.fontColor)
                tagRec = Rectangle(color=YELLOW, fill_color=YELLOW, fill_opacity=0.25, height=0.4, width=tagText.width+0.25)

                tagRec.next_to(self.prevRef, UP) 
                tagText.move_to(tagRec.get_center())

                self.prevRef = tagRec

                self.scene.play(Create(tagRec), Create(tagText), run_time=1/self.scene.args.speed)
                self.toFadeOut.add(tagRec, tagText)

                x += 1

                if i == 0:
                    self.topref = self.prevRef

    def draw_arrow(self, prevCircle, arrow):
        if ( prevCircle ):
            self.scene.play(Create(arrow), run_time=1/self.scene.args.speed)
            self.toFadeOut.add(arrow)

    def recenter_frame(self):
        self.scene.play(self.scene.camera.frame.animate.move_to(self.toFadeOut.get_center()), run_time=1/self.scene.args.speed)

    def scale_frame(self):
        self.scene.play(self.scene.camera.frame.animate.scale_to_fit_width(self.toFadeOut.get_width()*1.1), run_time=1/self.scene.args.speed)
        if ( self.toFadeOut.get_height() >= self.scene.camera.frame.get_height() ):
            self.scene.play(self.scene.camera.frame.animate.scale_to_fit_height(self.toFadeOut.get_height()*1.25), run_time=1/self.scene.args.speed)
