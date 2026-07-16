"""Blocking stdio server for the local assessment sidecar."""

from __future__ import annotations

import logging
from typing import BinaryIO

from pilot_assessment.sidecar.dispatcher import JsonRpcDispatcher
from pilot_assessment.sidecar.errors import JsonRpcFault
from pilot_assessment.sidecar.framing import (
    DEFAULT_MAX_MESSAGE_BYTES,
    JsonLineWriter,
    read_json_line,
)
from pilot_assessment.sidecar.methods import SidecarMethods


def serve(
    input_stream: BinaryIO,
    output_stream: BinaryIO,
    *,
    max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
    dispatcher: JsonRpcDispatcher | None = None,
    methods: SidecarMethods | None = None,
    logger: logging.Logger | None = None,
) -> int:
    """Serve JSON-RPC messages until EOF or an acknowledged shutdown request."""

    active_logger = logger or logging.getLogger(__name__)
    active_dispatcher = dispatcher or JsonRpcDispatcher(logger=active_logger)
    writer = JsonLineWriter(output_stream, max_message_bytes=max_message_bytes)
    active_methods = methods or SidecarMethods(notification_sink=writer.write)
    active_methods.register(active_dispatcher)

    try:
        while True:
            try:
                message = read_json_line(
                    input_stream,
                    max_message_bytes=max_message_bytes,
                )
            except JsonRpcFault as fault:
                writer.write(active_dispatcher.fault_response(fault))
                continue
            if message is None:
                break
            response = active_dispatcher.dispatch(message)
            if response is not None:
                writer.write(response)
            if active_methods.shutdown_requested:
                break
    finally:
        active_methods.close()
    return 0


__all__ = ["serve"]
