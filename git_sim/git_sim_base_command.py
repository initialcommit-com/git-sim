from manim import *
import git, sys, numpy, platform

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
        self.maxrefs = None
        self.i = 0
        self.numCommits = 5
        self.defaultNumCommits = 5
        self.selected_branches = []
        self.hide_first_tag = False
        self.stop = False
        self.zone_title_offset = 2.6 if platform.system() == "Windows" else 2.6

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

    def get_commits(self, start="HEAD"):
        if not self.numCommits:
            print("git-sim error: No commits in current Git repository.")
            sys.exit(1)

        try:
            self.commits = list(self.repo.iter_commits(start + "~" + str(self.numCommits) + "..." + start))
            if len(self.commits) < self.defaultNumCommits:
                self.commits = list(self.repo.iter_commits(start))
            while len(self.commits) < self.defaultNumCommits:
                self.commits.append(self.create_dark_commit())
            self.numCommits = self.defaultNumCommits;

        except git.exc.GitCommandError:
            self.numCommits -= 1
            self.get_commits(start=start)

    def parse_commits(self, commit, prevCircle=None, shift=numpy.array([0., 0., 0.])):
        if self.stop:
            return
        if ( self.i < self.numCommits and commit in self.commits ):
            commitId, circle, arrow, hide_refs = self.draw_commit(commit, prevCircle, shift)

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

            if self.i < len(self.commits)-1:
                self.i += 1
                self.parse_commits(self.commits[self.i], circle)
            else:
                self.i = 0

    def show_intro(self):
        if ( self.scene.args.animate and self.scene.args.show_intro ):
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
        if ( self.scene.args.animate and self.scene.args.show_outro ):

            self.scene.play(Restore(self.scene.camera.frame))

            self.scene.play(self.logo.animate.scale(4).set_x(0).set_y(0))

            outroTopText = Text(self.scene.args.outro_top_text, font="Monospace", font_size=36, color=self.scene.fontColor).to_edge(UP, buff=1)
            self.scene.play(AddTextLetterByLetter(outroTopText))

            outroBottomText = Text(self.scene.args.outro_bottom_text, font="Monospace", font_size=36, color=self.scene.fontColor).to_edge(DOWN, buff=1)
            self.scene.play(AddTextLetterByLetter(outroBottomText))

            self.scene.wait(3)

    def fadeout(self):
        if self.scene.args.animate:
            self.scene.wait(3)
            self.scene.play(FadeOut(self.toFadeOut), run_time=1/self.scene.args.speed)
        else:
            self.scene.wait(0.1)

    def get_centers(self):
        centers = []
        for commit in self.drawnCommits.values():
            centers.append(commit.get_center())
        return centers

    def draw_commit(self, commit, prevCircle, shift=numpy.array([0., 0., 0.])):
        if commit == "dark":
            commitFill = WHITE if self.scene.args.light_mode else BLACK
        elif ( len(commit.parents) <= 1 ):
            commitFill = RED 
        else:
            commitFill = GRAY

        circle = Circle(stroke_color=commitFill, fill_color=commitFill, fill_opacity=0.25)
        circle.height = 1 

        if shift.any():
            circle.shift(shift)

        if prevCircle:
            circle.next_to(prevCircle, RIGHT, buff=1.5)

        start = prevCircle.get_center() if prevCircle else LEFT
        end = circle.get_center()

        if commit == "dark":
            arrow = Arrow(start, end, color=WHITE if self.scene.args.light_mode else BLACK)
        elif commit.hexsha in self.drawnCommits:
            end = self.drawnCommits[commit.hexsha].get_center()
            arrow = Arrow(start, end, color=self.scene.fontColor)
            self.stop = True
        else:
            arrow = Arrow(start, end, color=self.scene.fontColor)

        length = numpy.linalg.norm(start-end) - ( 1.5 if start[1] == end[1] else 3  )
        arrow.set_length(length)

        commitId, commitMessage, commit, hide_refs = self.build_commit_id_and_message(commit)
        commitId.next_to(circle, UP)

        message = Text('\n'.join(commitMessage[j:j+20] for j in range(0, len(commitMessage), 20))[:100], font="Monospace", font_size=14, color=self.scene.fontColor).next_to(circle, DOWN)

        if self.scene.args.animate and commit != "dark" and not self.stop:
            self.scene.play(self.scene.camera.frame.animate.move_to(circle.get_center()), Create(circle), AddTextLetterByLetter(commitId), AddTextLetterByLetter(message), run_time=1/self.scene.args.speed)
        elif not self.stop:
            self.scene.add(circle, commitId, message)
        else:
            return commitId, circle, arrow, hide_refs

        if commit != "dark":
            self.drawnCommits[commit.hexsha] = circle

        self.toFadeOut.add(circle, commitId, message)
        self.prevRef = commitId

        return commitId, circle, arrow, hide_refs

    def build_commit_id_and_message(self, commit):
        hide_refs = False
        if commit == "dark":
            commitId = Text("", font="Monospace", font_size=20, color=self.scene.fontColor)
            commitMessage = ""
        else:
            commitId = Text(commit.hexsha[0:6], font="Monospace", font_size=20, color=self.scene.fontColor)
            commitMessage = commit.message[:40].replace("\n", " ")
        return commitId, commitMessage, commit, hide_refs

    def draw_head(self, commit, commitId):
        if ( commit.hexsha == self.repo.head.commit.hexsha ):
            headbox = Rectangle(color=BLUE, fill_color=BLUE, fill_opacity=0.25)
            headbox.width = 1 
            headbox.height = 0.4 
            headbox.next_to(commitId, UP) 
            headText = Text("HEAD", font="Monospace", font_size=20, color=self.scene.fontColor).move_to(headbox.get_center())

            head = VGroup(headbox, headText)

            if self.scene.args.animate:
                self.scene.play(Create(head), run_time=1/self.scene.args.speed)
            else:
                self.scene.add(head)

            self.toFadeOut.add(head)
            self.drawnRefs["HEAD"] = head
            self.prevRef = head

            if self.i == 0:
                self.topref = self.prevRef

    def draw_branch(self, commit):
        x = 0 
        branches = [branch.name for branch in self.repo.heads]
        for selected_branch in self.selected_branches:
            branches.insert(0, branches.pop(branches.index(selected_branch)))

        for branch in branches:

            if ( commit.hexsha == self.repo.heads[branch].commit.hexsha ):
                branchText = Text(branch, font="Monospace", font_size=20, color=self.scene.fontColor)
                branchRec = Rectangle(color=GREEN, fill_color=GREEN, fill_opacity=0.25, height=0.4, width=branchText.width+0.25)

                branchRec.next_to(self.prevRef, UP) 
                branchText.move_to(branchRec.get_center())

                fullbranch = VGroup(branchRec, branchText)

                self.prevRef = fullbranch

                if self.scene.args.animate:
                    self.scene.play(Create(fullbranch), run_time=1/self.scene.args.speed)
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

            if ( commit.hexsha == tag.commit.hexsha ):
                tagText = Text(tag.name, font="Monospace", font_size=20, color=self.scene.fontColor)
                tagRec = Rectangle(color=YELLOW, fill_color=YELLOW, fill_opacity=0.25, height=0.4, width=tagText.width+0.25)

                tagRec.next_to(self.prevRef, UP) 
                tagText.move_to(tagRec.get_center())

                self.prevRef = tagRec

                if self.scene.args.animate:
                    self.scene.play(Create(tagRec), Create(tagText), run_time=1/self.scene.args.speed)
                else:
                    self.scene.add(tagRec, tagText)

                self.toFadeOut.add(tagRec, tagText)

                if self.i == 0:
                    self.topref = self.prevRef

                x += 1
                if x >= self.scene.args.max_tags_per_commit:
                    return

    def draw_arrow(self, prevCircle, arrow):
        if prevCircle: 
            if self.scene.args.animate:
                self.scene.play(Create(arrow), run_time=1/self.scene.args.speed)
            else:
                self.scene.add(arrow)

            self.toFadeOut.add(arrow)

    def recenter_frame(self):
        if self.scene.args.animate:
            self.scene.play(self.scene.camera.frame.animate.move_to(self.toFadeOut.get_center()), run_time=1/self.scene.args.speed)
        else:
            self.scene.camera.frame.move_to(self.toFadeOut.get_center())

    def scale_frame(self):
        if self.scene.args.animate:
            self.scene.play(self.scene.camera.frame.animate.scale_to_fit_width(self.toFadeOut.get_width()*1.1), run_time=1/self.scene.args.speed)
            if ( self.toFadeOut.get_height() >= self.scene.camera.frame.get_height() ):
                self.scene.play(self.scene.camera.frame.animate.scale_to_fit_height(self.toFadeOut.get_height()*1.25), run_time=1/self.scene.args.speed)
        else:
            self.scene.camera.frame.scale_to_fit_width(self.toFadeOut.get_width()*1.1)
            if ( self.toFadeOut.get_height() >= self.scene.camera.frame.get_height() ):
                self.scene.camera.frame.scale_to_fit_height(self.toFadeOut.get_height()*1.25)

    def vsplit_frame(self):
        if self.scene.args.animate:
            self.scene.play(self.scene.camera.frame.animate.scale_to_fit_height(self.scene.camera.frame.get_height()*2))
        else:
            self.scene.camera.frame.scale_to_fit_height(self.scene.camera.frame.get_height()*2)

        try:
            if self.scene.args.animate:
                self.scene.play(self.toFadeOut.animate.align_to(self.scene.camera.frame, UP).shift(DOWN*0.75))
            else:
                self.toFadeOut.align_to(self.scene.camera.frame, UP).shift(DOWN*0.75)
        except ValueError:
            pass

    def setup_and_draw_zones(self, first_column_name="Untracked files", second_column_name="Working directory modifications", third_column_name="Staging area", reverse=False):
        horizontal = Line((self.scene.camera.frame.get_left()[0], self.scene.camera.frame.get_center()[1], 0), (self.scene.camera.frame.get_right()[0], self.scene.camera.frame.get_center()[1], 0), color=self.scene.fontColor).shift(UP*2.5)
        horizontal2 = Line((self.scene.camera.frame.get_left()[0], self.scene.camera.frame.get_center()[1], 0), (self.scene.camera.frame.get_right()[0], self.scene.camera.frame.get_center()[1], 0), color=self.scene.fontColor).shift(UP*1.5)
        vert1 = DashedLine((self.scene.camera.frame.get_left()[0], self.scene.camera.frame.get_bottom()[1], 0), (self.scene.camera.frame.get_left()[0], horizontal.get_start()[1], 0), dash_length=0.2, color=self.scene.fontColor).shift(RIGHT*6.5)
        vert2 = DashedLine((self.scene.camera.frame.get_right()[0], self.scene.camera.frame.get_bottom()[1], 0), (self.scene.camera.frame.get_right()[0], horizontal.get_start()[1], 0), dash_length=0.2, color=self.scene.fontColor).shift(LEFT*6.5)

        if reverse:
            first_column_name = "Staging area"
            third_column_name = "Deleted changes"

        firstColumnTitle = Text(first_column_name, font="Monospace", font_size=28, color=self.scene.fontColor).align_to(self.scene.camera.frame, LEFT).shift(RIGHT*0.65).shift(UP*self.zone_title_offset)
        secondColumnTitle = Text(second_column_name, font="Monospace", font_size=28, color=self.scene.fontColor).move_to(self.scene.camera.frame.get_center()).align_to(firstColumnTitle, UP)
        thirdColumnTitle = Text(third_column_name, font="Monospace", font_size=28, color=self.scene.fontColor).align_to(self.scene.camera.frame, RIGHT).shift(LEFT*1.65).align_to(firstColumnTitle, UP)

        self.toFadeOut.add(horizontal, horizontal2, vert1, vert2, firstColumnTitle, secondColumnTitle, thirdColumnTitle)

        if self.scene.args.animate:
            self.scene.play(Create(horizontal), Create(horizontal2), Create(vert1), Create(vert2), AddTextLetterByLetter(firstColumnTitle), AddTextLetterByLetter(secondColumnTitle), AddTextLetterByLetter(thirdColumnTitle)) 
        else:
            self.scene.add(horizontal, horizontal2, vert1, vert2, firstColumnTitle, secondColumnTitle, thirdColumnTitle)

        firstColumnFileNames = set()
        secondColumnFileNames = set()
        thirdColumnFileNames = set()

        firstColumnArrowMap = {}
        secondColumnArrowMap = {}

        self.populate_zones(firstColumnFileNames, secondColumnFileNames, thirdColumnFileNames, firstColumnArrowMap, secondColumnArrowMap)

        firstColumnFiles = VGroup()
        secondColumnFiles = VGroup()
        thirdColumnFiles = VGroup()

        firstColumnFilesDict = {}
        secondColumnFilesDict = {}
        thirdColumnFilesDict = {}

        for i, f in enumerate(firstColumnFileNames):
            text = Text(f, font="Monospace", font_size=24, color=self.scene.fontColor).move_to((firstColumnTitle.get_center()[0], horizontal2.get_center()[1], 0)).shift(DOWN*0.5*(i+1))
            firstColumnFiles.add(text)
            firstColumnFilesDict[f] = text

        for j, f in enumerate(secondColumnFileNames):
            text = Text(f, font="Monospace", font_size=24, color=self.scene.fontColor).move_to((secondColumnTitle.get_center()[0], horizontal2.get_center()[1], 0)).shift(DOWN*0.5*(j+1))
            secondColumnFiles.add(text)
            secondColumnFilesDict[f] = text

        for h, f in enumerate(thirdColumnFileNames):
            text = Text(f, font="Monospace", font_size=24, color=self.scene.fontColor).move_to((thirdColumnTitle.get_center()[0], horizontal2.get_center()[1], 0)).shift(DOWN*0.5*(h+1))
            thirdColumnFiles.add(text)
            thirdColumnFilesDict[f] = text

        if len(firstColumnFiles):
            if self.scene.args.animate:
                self.scene.play(*[AddTextLetterByLetter(d) for d in firstColumnFiles])
            else:
                self.scene.add(*[d for d in firstColumnFiles])

        if len(secondColumnFiles):
            if self.scene.args.animate:
                self.scene.play(*[AddTextLetterByLetter(w) for w in secondColumnFiles])
            else:
                self.scene.add(*[w for w in secondColumnFiles])

        if len(thirdColumnFiles):
            if self.scene.args.animate:
                self.scene.play(*[AddTextLetterByLetter(s) for s in thirdColumnFiles])
            else:
                self.scene.add(*[s for s in thirdColumnFiles])

        for filename in firstColumnArrowMap:
            if reverse:
                firstColumnArrowMap[filename].put_start_and_end_on((firstColumnFilesDict[filename].get_right()[0]+0.25, firstColumnFilesDict[filename].get_right()[1], 0), (secondColumnFilesDict[filename].get_left()[0]-0.25, secondColumnFilesDict[filename].get_left()[1], 0))
            else:
                firstColumnArrowMap[filename].put_start_and_end_on((firstColumnFilesDict[filename].get_right()[0]+0.25, firstColumnFilesDict[filename].get_right()[1], 0), (thirdColumnFilesDict[filename].get_left()[0]-0.25, thirdColumnFilesDict[filename].get_left()[1], 0))
            if self.scene.args.animate:
                self.scene.play(Create(firstColumnArrowMap[filename]))
            else:
                self.scene.add(firstColumnArrowMap[filename])
            self.toFadeOut.add(firstColumnArrowMap[filename])

        for filename in secondColumnArrowMap:
            secondColumnArrowMap[filename].put_start_and_end_on((secondColumnFilesDict[filename].get_right()[0]+0.25, secondColumnFilesDict[filename].get_right()[1], 0), (thirdColumnFilesDict[filename].get_left()[0]-0.25, thirdColumnFilesDict[filename].get_left()[1], 0))
            if self.scene.args.animate:
                self.scene.play(Create(secondColumnArrowMap[filename]))
            else:
                self.scene.add(secondColumnArrowMap[filename])
            self.toFadeOut.add(secondColumnArrowMap[filename])

        self.toFadeOut.add(firstColumnFiles, secondColumnFiles, thirdColumnFiles)

    def populate_zones(self, firstColumnFileNames, secondColumnFileNames, thirdColumnFileNames, firstColumnArrowMap={}, secondColumnArrowMap={}):

        for x in self.repo.index.diff(None):
            if "git-sim_media" not in x.a_path:
                secondColumnFileNames.add(x.a_path)

        for y in self.repo.index.diff("HEAD"):
            if "git-sim_media" not in y.a_path:
                thirdColumnFileNames.add(y.a_path)

        for z in self.repo.untracked_files:
            if "git-sim_media" not in z:
                firstColumnFileNames.add(z)

    def center_frame_on_commit(self, commit):
        if self.scene.args.animate:
            self.scene.play(self.scene.camera.frame.animate.move_to(self.drawnCommits[commit.hexsha].get_center()))
        else:
            self.scene.camera.frame.move_to(self.drawnCommits[commit.hexsha].get_center())

    def reset_head_branch(self, hexsha, shift=numpy.array([0., 0., 0.])):
        if self.scene.args.animate:
            self.scene.play(self.drawnRefs["HEAD"].animate.move_to((self.drawnCommits[hexsha].get_center()[0]+shift[0], self.drawnCommits[hexsha].get_center()[1]+1.4+shift[1], 0)),
                            self.drawnRefs[self.repo.active_branch.name].animate.move_to((self.drawnCommits[hexsha].get_center()[0]+shift[0], self.drawnCommits[hexsha].get_center()[1]+2+shift[1], 0)))
        else:
            self.drawnRefs["HEAD"].move_to((self.drawnCommits[hexsha].get_center()[0]+shift[0], self.drawnCommits[hexsha].get_center()[1]+1.4+shift[1], 0))
            self.drawnRefs[self.repo.active_branch.name].move_to((self.drawnCommits[hexsha].get_center()[0]+shift[0], self.drawnCommits[hexsha].get_center()[1]+2+shift[1], 0))

    def translate_frame(self, shift):
        if self.scene.args.animate:
            self.scene.play(self.scene.camera.frame.animate.shift(shift))
        else:
            self.scene.camera.frame.shift(shift)

    def setup_and_draw_parent(self, child, commitMessage="New commit", shift=numpy.array([0., 0., 0.]), draw_arrow=True):
        circle = Circle(stroke_color=RED, fill_color=RED, fill_opacity=0.25)
        circle.height = 1 
        circle.next_to(self.drawnCommits[child.hexsha], LEFT, buff=1.5)
        circle.shift(shift)

        start = circle.get_center()
        end = self.drawnCommits[child.hexsha].get_center()
        arrow = Arrow(start, end, color=self.scene.fontColor)
        length = numpy.linalg.norm(start-end) - ( 1.5 if start[1] == end[1] else 3  )
        arrow.set_length(length)

        commitId = Text("abcdef", font="Monospace", font_size=20, color=self.scene.fontColor).next_to(circle, UP) 
        self.toFadeOut.add(commitId)

        commitMessage = commitMessage[:40].replace("\n", " ")
        message = Text('\n'.join(commitMessage[j:j+20] for j in range(0, len(commitMessage), 20))[:100], font="Monospace", font_size=14, color=self.scene.fontColor).next_to(circle, DOWN)
        self.toFadeOut.add(message)

        if self.scene.args.animate:
            self.scene.play(self.scene.camera.frame.animate.move_to(circle.get_center()), Create(circle), AddTextLetterByLetter(commitId), AddTextLetterByLetter(message), run_time=1/self.scene.args.speed)
        else:
            self.scene.camera.frame.move_to(circle.get_center())
            self.scene.add(circle, commitId, message)

        self.drawnCommits["abcdef"] = circle
        self.toFadeOut.add(circle)

        if draw_arrow:
            if self.scene.args.animate:
                self.scene.play(Create(arrow), run_time=1/self.scene.args.speed)
            else:
                self.scene.add(arrow)
            self.toFadeOut.add(arrow)

        return commitId

    def draw_arrow_between_commits(self, startsha, endsha):
        start = self.drawnCommits[startsha].get_center()
        end = self.drawnCommits[endsha].get_center()

        arrow = DottedLine(start, end, color=self.scene.fontColor).add_tip()
        length = numpy.linalg.norm(start-end) - 1.65
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

    def draw_ref(self, commit, top, text="HEAD", color=BLUE):
        refText = Text(text, font="Monospace", font_size=20, color=self.scene.fontColor)
        refbox = Rectangle(color=color, fill_color=color, fill_opacity=0.25, height=0.4, width=refText.width+0.25)
        refbox.next_to(top, UP) 
        refText.move_to(refbox.get_center())

        ref = VGroup(refbox, refText)

        if self.scene.args.animate:
            self.scene.play(Create(ref), run_time=1/self.scene.args.speed)
        else:
            self.scene.add(ref)

        self.toFadeOut.add(ref)
        self.drawnRefs[text] = ref
        self.prevRef = ref

        if self.i == 0:
            self.topref = self.prevRef

    def draw_dark_ref(self):
        refRec = Rectangle(color=WHITE if self.scene.args.light_mode else BLACK, fill_color=WHITE if self.scene.args.light_mode else BLACK, height=0.4, width=1)
        refRec.next_to(self.prevRef, UP)
        self.scene.add(refRec)
        self.toFadeOut.add(refRec)
        self.prevRef = refRec


class DottedLine(Line):

    def __init__(self, *args, dot_spacing=0.4, dot_kwargs={}, **kwargs):
        Line.__init__(self, *args, **kwargs)
        n_dots = int(self.get_length() / dot_spacing) + 1
        dot_spacing = self.get_length() / (n_dots - 1)
        unit_vector = self.get_unit_vector()
        start = self.start

        self.dot_points = [start + unit_vector * dot_spacing * x for x in range(n_dots)]
        self.dots = [Dot(point, **dot_kwargs) for point in self.dot_points]

        self.clear_points()

        self.add(*self.dots)

        self.get_start = lambda: self.dot_points[0]
        self.get_end = lambda: self.dot_points[-1]

    def get_first_handle(self):
        return self.dot_points[-1]

    def get_last_handle(self):
        return self.dot_points[-2]
