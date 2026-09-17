"""Animation stand-ins for static rendering.

A static image only needs the final state, so each animation knows how to
apply its end state to the scene when played: Create adds, FadeOut removes,
ReplacementTransform swaps, Restore restores. ``mobject.animate.method(...)``
applies the method immediately and returns a chainable proxy.
"""


class Animation:
    def __init__(self, mobject=None, **kwargs):
        self.mobject = mobject
        self.kwargs = kwargs

    def apply(self, scene):
        pass


class Create(Animation):
    def apply(self, scene):
        if self.mobject is not None:
            scene.add(self.mobject)


class Write(Create):
    pass


class FadeIn(Create):
    pass


class AddTextLetterByLetter(Create):
    pass


class GrowFromCenter(Create):
    pass


class FadeOut(Animation):
    def apply(self, scene):
        if self.mobject is not None:
            scene.remove(self.mobject)


class Uncreate(FadeOut):
    pass


class Unwrite(FadeOut):
    pass


class Transform(Animation):
    def __init__(self, mobject, target_mobject=None, **kwargs):
        super().__init__(mobject, **kwargs)
        self.target = target_mobject

    def apply(self, scene):
        if self.mobject is None or self.target is None:
            return
        state = dict(self.target.__dict__)
        state.pop("_saved_state", None)
        self.mobject.__dict__.update(state)
        scene.add(self.mobject)


class ReplacementTransform(Transform):
    def apply(self, scene):
        if self.mobject is not None:
            scene.remove(self.mobject)
        if self.target is not None:
            scene.add(self.target)


class Restore(Animation):
    def apply(self, scene):
        if self.mobject is not None:
            self.mobject.restore()


class AnimationGroup(Animation):
    def __init__(self, *animations, **kwargs):
        super().__init__(None, **kwargs)
        self.animations = animations

    def apply(self, scene):
        for animation in self.animations:
            apply_animation(animation, scene)


class Succession(AnimationGroup):
    pass


class LaggedStart(AnimationGroup):
    pass


class Wait(Animation):
    pass


class AnimateProxy:
    """``mobject.animate`` — runs each chained method on the mobject at once."""

    def __init__(self, mobject):
        self._mobject = mobject

    def __call__(self, **kwargs):
        return self

    def __getattr__(self, name):
        method = getattr(self._mobject, name)

        def call(*args, **kwargs):
            method(*args, **kwargs)
            return self

        return call

    def build(self):
        return self

    def apply(self, scene):
        pass


def apply_animation(animation, scene):
    apply = getattr(animation, "apply", None)
    if callable(apply):
        apply(scene)
