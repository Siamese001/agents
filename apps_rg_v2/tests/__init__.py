"""Repository test package.

Keeping the test tree under an explicit top-level package prevents its
``apps_rg`` and ``apps_research`` directories from shadowing the production
packages during whole-repository pytest collection.
"""
