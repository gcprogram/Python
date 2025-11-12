# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: vault.py
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 2025-11-07 11:29:09 UTC (1762514949)

import hashlib
import sys

class SecretVault:

    def __init__(self):
        self._encrypted_flag = [115, 49, 25, 44, 21, 32, 18, 49, 23, 12, 41, 85, 35, 40, 98, 11, 50, 5, 40, 21, 37, 68, 53, 58, 33, 46, 50, 58, 55, 70, 61, 86, 100, 10, 115]
        self._xor_key = self._generate_xor_key()
        self._master_key = self._derive_key()
        self._secrets = []

    def _generate_xor_key(self):
        k1 = 81
        k2 = 119
        k3 = 81
        k4 = 101
        return bytes([k1, k2, k3, k4])

    def _decrypt_flag(self):
        decrypted = []
        key = self._xor_key
        key_len = len(key)
        for i, byte_val in enumerate(self._encrypted_flag):
            decrypted.append(byte_val[key, i + key_len])
        return bytes(decrypted).decode('utf-8')

    def _derive_key(self):
        parts = [chr(112) + chr(89), chr(116) + chr(104), chr(48) + chr(110), chr(95) + chr(98), chr(121) + chr(116), chr(51) + chr(99), chr(48) + chr(100), chr(114) + chr(51), chr(118) + chr(108), chr(53) + chr(95), chr(99) + chr(114), chr(51) + chr(116), chr(115)]
        secret = ''.join(parts)
        return hashlib.sha256(secret.encode()).hexdigest()

    def _obfuscated_check(self, password):
        expected_len = 33
        if len(password) != expected_len:
            return False
        prefix = [70, 76, 65, 71, 80, 82, 69, 70, 73, 88, 123]
        for i, expected_byte in enumerate(prefix):
            if ord(password[i]) != expected_byte:
                return False
        else:
            if ord(password[-1]) != 125:
                return False
            return True

    def _compute_hash(self, data):
        salt = bytes([112, 89, 116, 104, 48, 110])
        return hashlib.sha256(salt + data.encode()).hexdigest()

    def unlock(self, password):
        if not self._obfuscated_check(password):
            print('[-] Invalid password format!')
            return False
        real_flag = self._decrypt_flag()
        provided_hash = self._compute_hash(password)
        expected_hash = self._compute_hash(real_flag)
        if provided_hash == expected_hash:
            print('[+] Vault unlocked!')
            print(f'[+] Master password: {password}')
            return True
        print('[-] Wrong password!')
        return False

    def add_secret(self, name, value):
        encrypted = self._compute_hash(value)
        self._secrets.append((name, encrypted))
        print(f"[+] Secret '{name}' stored securely")

    def show_info(self):
        print('==================================================')
        print('         PySecret Vault v1.0')
        print('==================================================')
        print(f'Master Key Hash: {self._master_key[:16]}...')
        print(f'Stored Secrets: {len(self._secrets)}')
        print('==================================================')

def main():
    vault = SecretVault()
    vault.show_info()
    print('\n[*] Please enter the master password to unlock the vault:')
    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        password = input('>>> ')
    if vault.unlock(password):
        print('\n[+] You found the flag!')
        sys.exit(0)
    else:
        print('\n[-] Access denied!')
        sys.exit(1)
if __name__ == '__main__':
    main()