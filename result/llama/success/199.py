from balance_bridge.errors import (
    KeystoreFetchError,
    KeystoreWriteError,
    KeystoreTokenExpiredError,
)
import aioredis as redis


class RedisKeystore(object):

    def __init__(
        self, host="localhost", port=6379, db=0, charset="utf-8", decode_responses=True
    ):
        self.redis_keystore = redis.Redis(
            host=host,
            port=port,
            db=db,
            encoding=charset,
            decode_responses=decode_responses,
        )

    def connection_key(self, token):
        return "conn:{}".format(token)

    def transaction_key(self, transaction_uuid, device_uuid):
        return "txn:{}:{}".format(transaction_uuid, device_uuid)

    async def write(
        self, key, value="", expiration_in_seconds=120, write_only_if_exists=False
    ):
        success = await self.redis_keystore.set(key, value, ex=expiration_in_seconds)
        return success

    def add_shared_connection(self, token):
        key = self.connection_key(token)
        success = self.write(key)
        if not success:
            raise KeystoreWriteError

    def update_connection_details(self, token, encrypted_payload):
        key = self.connection_key(token)
        success = self.write(key, encrypted_payload, write_only_if_exists=True)
        if not success:
            raise KeystoreTokenExpiredError

    async def pop_connection_details(self, token):
        key = self.connection_key(token)
        details = await self.redis_keystore.get(key)
        if details:
            await self.redis_keystore.delete(key)
        return details

    def add_transaction(self, transaction_uuid, device_uuid, encrypted_payload):
        key = self.transaction_key(transaction_uuid, device_uuid)
        success = self.write(key, encrypted_payload)
        if not success:
            raise KeystoreWriteError

    async def pop_transaction_details(self, transaction_uuid, device_uuid):
        key = self.transaction_key(transaction_uuid, device_uuid)
        details = await self.redis_keystore.get(key)
        if not details:
            raise KeystoreFetchError
        else:
            await self.redis_keystore.delete(key)
            return details
