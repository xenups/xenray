"""Async animation loop coroutines for ConnectionButton."""

from __future__ import annotations

import asyncio
import math
from typing import Callable

import flet as ft


async def connected_breath_loop(
    has_page: Callable[[], bool],
    glow_layer: ft.Container,
    is_active: Callable[[], bool],
    get_activity: Callable[[], float],
) -> None:
    """Idle breathing pulse for the connected state when network activity is low."""
    grow = True
    while is_active():
        if not has_page():
            break
        try:
            if get_activity() < 5:
                if grow:
                    glow_layer.opacity = 0.8
                    glow_layer.scale = 1.02
                else:
                    glow_layer.opacity = 0.5
                    glow_layer.scale = 1.0
                glow_layer.update()

            grow = not grow
            await asyncio.sleep(1.2)
        except asyncio.CancelledError:
            break
        except Exception:
            break


async def connecting_pulse_loop(
    has_page: Callable[[], bool],
    glow_layer: ft.Container,
    is_active: Callable[[], bool],
) -> None:
    """Pulse animation loop for the connecting state."""
    grow = True
    while is_active():
        if not has_page():
            break
        try:
            if grow:
                glow_layer.opacity = 0.75
                glow_layer.scale = 1.02
            else:
                glow_layer.opacity = 0.4
                glow_layer.scale = 1.0

            glow_layer.update()
            grow = not grow
            await asyncio.sleep(0.8)
        except asyncio.CancelledError:
            break
        except Exception:
            break


async def disconnecting_pulse_loop(
    has_page: Callable[[], bool],
    glow_layer: ft.Container,
    is_active: Callable[[], bool],
) -> None:
    """Rapid pulse animation loop for the disconnecting state."""
    grow = True
    while is_active():
        if not has_page():
            break
        try:
            if grow:
                glow_layer.opacity = 0.75
                glow_layer.scale = 1.02
            else:
                glow_layer.opacity = 0.4
                glow_layer.scale = 1.0

            glow_layer.update()
            grow = not grow
            await asyncio.sleep(0.4)
        except asyncio.CancelledError:
            break
        except Exception:
            break


async def ping_sweep_loop(
    border_container: ft.Container,
    is_animating: Callable[[], bool],
) -> None:
    """Drive native GPU rotation of the sweep disc while pinging."""
    try:
        # Frame flush: let the rotate=0.0 anchor render before nudging
        await asyncio.sleep(0.05)
        if not is_animating():
            return
        full_turns = 0
        while is_animating():
            full_turns += 1
            border_container.rotate = ft.Rotate(angle=2 * math.pi * full_turns)
            try:
                border_container.update()
            except Exception:
                pass
            await asyncio.sleep(1.4)
    except asyncio.CancelledError:
        pass
    except Exception:
        pass
    finally:
        border_container.rotate = ft.Rotate(angle=0.0)
