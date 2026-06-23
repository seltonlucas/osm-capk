#!/usr/bin/python3
# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from hashlib import sha256
import bcrypt


def hash_password(password: str, rounds: int = 12) -> str:
    """
    Hash a password with a given number of rounds and return as hex.

    Args:
    - password (str): The password to hash.
    - rounds (int): The number of rounds (log_rounds) for bcrypt. Default is 12.

    Returns:
    - str: The hashed password as an hex string.
    """
    # Generate a salt with the specified number of rounds
    salt = bcrypt.gensalt(rounds=rounds)

    # Hash the password using the generated salt
    hashed_password = bcrypt.hashpw(password.encode("utf-8"), salt)

    # Return the hashed password and salt as hex strings
    return hashed_password.hex()


def verify_password(password: str, hashed_password_hex: str) -> bool:
    """
    Verify a password against a hashed password provided as hex.

    Args:
    - password (str): The password to verify.
    - hashed_password_hex (str): The hashed password as a hex string.

    Returns:
    - bool: True if the password matches the hashed password, False otherwise.
    """
    # Convert the hashed password from hex to bytes
    hashed_password = bytes.fromhex(hashed_password_hex)

    # Verify the password against the hashed password
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password)


def verify_password_sha256(password: str, hashed_password_hex: str, salt: str) -> bool:
    """
    [Function for backwards compatibility using the SHA256]
    Verify a password against a hashed password provided as hex.

    Args:
    - password (str): The password to verify.
    - hashed_password_hex (str): The hashed password as a hex string.
    - salt (str): The salt used to hash the password as a hex string.

    Returns:
    - bool: True if the password matches the hashed password, False otherwise.
    """
    # Old verification for backwards compatibility
    shadow_password = sha256(
        password.encode("utf-8") + salt.encode("utf-8")
    ).hexdigest()

    return shadow_password == hashed_password_hex
