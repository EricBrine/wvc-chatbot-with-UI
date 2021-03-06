import sys
# sys.path.append("venv/lib/python3.6/site-packages/")
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import logging
logging.getLogger("tensorflow").setLevel(logging.ERROR)

import asyncio
import inspect
import json
import uuid
import warnings
from asyncio import Queue, CancelledError
from sanic import Sanic, Blueprint, response
from sanic.log import logger
from sanic.request import Request
from typing import Text, List, Dict, Any, Optional, Callable, Iterable, Awaitable

import rasa.utils.endpoints
from rasa.cli import utils as cli_utils
from rasa.constants import DOCS_BASE_URL
from rasa.core import utils
from rasa.core.channels.channel import InputChannel, UserMessage, CollectingOutputChannel, register
from rasa.core.agent import Agent
import rasa.core.run as run
from rasa.utils.common import raise_warning, update_sanic_log_level
from rasa.constants import (
    DEFAULT_DOMAIN_PATH,
    LEGACY_DOCS_BASE_URL,
    ENV_SANIC_BACKLOG,
    DEFAULT_CORE_SUBDIRECTORY_NAME,
)
from sanic.response import HTTPResponse
from typing import NoReturn

from rasa.utils.endpoints import EndpointConfig
from flask import Flask, request, json

warnings.filterwarnings(action='ignore', category=DeprecationWarning)
action_endpoint = EndpointConfig('http://localhost:5055/webhook')

class RestInput(InputChannel):

	@classmethod
	def name(cls) -> Text:
		return "rest"

	@staticmethod
	async def on_message_wrapper(
		on_new_message: Callable[[UserMessage], Awaitable[Any]],
		text: Text,
		queue: Queue,
		sender_id: Text,
		input_channel: Text,
		metadata: Optional[Dict[Text, Any]],
	) -> None:
		collector = QueueOutputChannel(queue)

		message = UserMessage(
			text, collector, sender_id, input_channel=input_channel, metadata=metadata
		)
		await on_new_message(message)

		await queue.put("DONE")  # pytype: disable=bad-return-type

	async def _extract_sender(self, req: Request) -> Optional[Text]:
		return req.json.get("sender", None)

	# noinspection PyMethodMayBeStatic
	def _extract_message(self, req: Request) -> Optional[Text]:
		return req.json.get("message", None)

	def _extract_input_channel(self, req: Request) -> Text:
		return req.json.get("input_channel") or self.name()

	def stream_response(
		self,
		on_new_message: Callable[[UserMessage], Awaitable[None]],
		text: Text,
		sender_id: Text,
		input_channel: Text,
		metadata: Optional[Dict[Text, Any]],
	) -> Callable[[Any], Awaitable[None]]:
		async def stream(resp: Any) -> None:
			q = Queue()
			task = asyncio.ensure_future(
				self.on_message_wrapper(
					on_new_message, text, q, sender_id, input_channel, metadata
				)
			)
			result = None  # declare variable up front to avoid pytype error
			while True:
				result = await q.get()
				if result == "DONE":
					break
				else:
					await resp.write(json.dumps(result) + "\n")
			await task

		return stream  # pytype: disable=bad-return-type

	def blueprint(
		self, on_new_message: Callable[[UserMessage], Awaitable[None]]
	) -> Blueprint:
		custom_webhook = Blueprint(
			"custom_webhook_{}".format(type(self).__name__),
			inspect.getmodule(self).__name__,
		)

		# noinspection PyUnusedLocal
		@custom_webhook.route("/", methods=["GET"])
		async def health(request: Request) -> HTTPResponse:
			return response.json({"status": "ok"})

		@custom_webhook.route("/hi", methods=["GET"])
		async def hi(request: Request) -> HTTPResponse:
			return response.json({"hi": "hi"})

		@custom_webhook.route("/webhook", methods=["POST"])
		async def receive(request: Request) -> HTTPResponse:
			sender_id = await self._extract_sender(request)
			text = self._extract_message(request)
			should_use_stream = rasa.utils.endpoints.bool_arg(
				request, "stream", default=False
			)
			input_channel = self._extract_input_channel(request)
			metadata = self.get_metadata(request)

			if should_use_stream:
				return response.stream(
					self.stream_response(
						on_new_message, text, sender_id, input_channel, metadata
					),
					content_type="text/event-stream",
				)
			else:
				collector = CollectingOutputChannel()
				# noinspection PyBroadException
				try:
					await on_new_message(
						UserMessage(
							text,
							collector,
							sender_id,
							input_channel=input_channel,
							metadata=metadata,
						)
					)
				except CancelledError:
					logger.error(
						"Message handling timed out for "
						"user message '{}'.".format(text)
					)
				except Exception:
					logger.exception(
						"An exception occured while handling "
						"user message '{}'.".format(text)
					)
				return response.json(collector.messages)

		return custom_webhook


if __name__ == '__main__':

	agent = Agent.load('rasa_backend/models/current', action_endpoint = action_endpoint)
	input_channel = RestInput()
	logger.info('Here is your log1')
	logger.warning('Here is your log2')
	app = run.configure_app([input_channel], None, None, enable_api=False, route='/webhooks/')

	app.agent = agent

	# update_sanic_log_level()
	print(type(app))
	app.debug=bool(os.environ.get('DEBUG', ''))
	app.run(
		host="0.0.0.0",
		port=8000,
		debug=True,
		backlog=int(os.environ.get(ENV_SANIC_BACKLOG, "100")),
	)
	app.configure_logging = True

	logger.info('Here is your log3')
	# run()


