from __future__ import annotations


class StaticAttrs:
    def get_attributes(self, user):
        return {"role": "admin"}


class SelfSignupContext:
    def get_context(self, user, action, resource):
        return {"allow": {"self_signup": True}}


class Missing:
    pass
