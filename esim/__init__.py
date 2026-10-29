"""Explained by Simulation: the long-form video engine.

Every video is generated from scratch. Scenes are Python functions that draw a frame at time t
using the toolkit in esim.engine, so nothing rendered is ever reused between videos.
"""
