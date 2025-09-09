from math import ceil
from ndef import message_encoder, Record
from smartcard.ATR import ATR
from smartcard.CardConnection import CardConnection
from smartcard.CardRequest import CardRequest
from smartcard.util import toHexString
from smartcard.Exceptions import CardRequestTimeoutException, CardConnectionException
from typing import Callable

from tag import Tag

class Reader:
    verbose: bool = False
    device: CardRequest
    tag: Tag
    max_bytes_per_read: int

    def __init__(self, tag: Tag, max_bytes_per_read: int, verbose: bool = False, timeout_sec: int = 3600):
        self.device = CardRequest(timeout=timeout_sec, cardType=tag.atr)
        self.tag = tag
        self.verbose = verbose
        self.max_bytes_per_read = max_bytes_per_read

    def _log(self, text: str):
        if self.verbose:
            print(text)

    def _log_card_info(self, connection: CardConnection):
        if not self.verbose:
            return

        atr_raw = connection.getATR()
        if not atr_raw:
            print("No ATR sent by card.")
            return
        atr = ATR(atr_raw)

        print("------ CARD INFO -------")
        print("Raw ATR: ", atr_raw)
        print("Historical bytes: ", toHexString(atr.getHistoricalBytes()))
        print(f"Checksum: 0x{atr.getChecksum():02X}")
        print("Checksum OK: ", atr.checksumOK)
        print("T0 supported: ", atr.isT0Supported())
        print("T1 supported: ", atr.isT1Supported())
        print("T15 supported: ", atr.isT15Supported())
        print("------ END CARD INFO -------\n")

    def read_card(self, card: CardConnection) -> bytes:
        """
        Reads content of NDEF + TLV formatted records
        """
        ndef_tlv_terminator = 0xFE
        ndef_tlv_start = 0x03

        content = bytearray()
        current_byte_index = 0
        page_index = self.tag.memory_page_start

        read_length = self.max_bytes_per_read
        pages_per_read = self.max_bytes_per_read // self.tag.bytes_per_page
        max_header_length = 4

        self._log("Reading card..")
        while True:
            pages_data = self._read_card_bytes(card, page_index, read_length)
            page_index += pages_per_read
            content.extend(pages_data)

            content_length = current_byte_index + read_length
            for current_byte_index in range(current_byte_index, content_length):
                current_byte = content[current_byte_index]

                if current_byte == 0x00: # Skip null bytes
                    current_byte_index += 1
                    continue

                if current_byte == ndef_tlv_terminator:
                    print("No record found.")
                    return bytes()

                header_length = 2
                if current_byte == ndef_tlv_start:
                    self._log(f"Found NDEF TLV at byte {current_byte_index}")
                    contains_header = len(content) >= current_byte_index + max_header_length
                    if not contains_header: # If we are getting too close to the end of the buffer, load more data
                        self._log("Current buffer does not contain header. Reading more pages...")
                        pages_data = self._read_card_bytes(card, page_index, read_length)
                        page_index += pages_per_read
                        content.extend(pages_data)

                    record_length = content[current_byte_index + 1]
                    if record_length == 0xFF:
                        header_length = 4 
                        record_length = content[current_byte_index + 2] << 8 | content[current_byte_index + 3] # Forgive me

                    record_start = current_byte_index + header_length
                    record_end = record_start + record_length
                    self._log(f"Record should be from byte {hex(record_start)} to {hex(record_end)}")

                    pages_data = self._read_card_bytes(card, page_index, header_length + record_length)
                    content.extend(pages_data)

                    return bytes(content[record_start : record_end])

    def write_card(self, card: CardConnection, mime_type: str, content: bytes):
        print(f"Writing to card: {mime_type} - {content}")
        record = Record(mime_type, '1', content)
        encoder = message_encoder()
        encoder.send(None) # Don't ask any questions
        encoder.send(record)
        message = encoder.send(None) # Really, please don't
        if not message or not isinstance(message, bytes):
            raise ValueError("Could not encode NDEF message.", message)

        tlv_start = 0x03
        tlv_end = 0xFE
        tlv_header = bytes([tlv_start, len(message)])
        tlv_message = tlv_header + message + bytes(tlv_end)

        # Fill the unused bytes in page
        bytes_in_last_page = len(tlv_message) % self.tag.bytes_per_page
        if bytes_in_last_page != 0: # 0 if the page doesn't have empty space
            padding = bytes(self.tag.bytes_per_page - bytes_in_last_page)
            tlv_message += padding

        message_size = len(tlv_message)
        max_page_amount = self.tag.memory_page_max - self.tag.memory_page_start
        max_bytes_in_memory = max_page_amount * self.tag.bytes_per_page
        if message_size > max_bytes_in_memory:
            raise ValueError(f"NDEF Message is too large for the given tag. The max size is {max_bytes_in_memory} bytes and the current message is {message_size} bytes")

        self._write_card_bytes(card, self.tag.memory_page_start, tlv_message)
        print("Card written.")

    def wait_for_card(self, callback: Callable, *callback_args):
        print("Waiting for card...")
        try:
            service = self.device.waitforcard()
        except CardRequestTimeoutException:
            print("Card wait timed out.")
            return None
        
        if not service:
            print("No card found.")
            return None
        
        connection = service.connection
        connection.connect()
        self._log_card_info(connection)
        try:
            return callback(connection, *callback_args)
        finally:
            self._log("Closing connection with card")
            connection.disconnect()
            connection.release()

    def _read_card_bytes(self, card: CardConnection, page: int, length_in_bytes: int) -> bytes:
        raise NotImplementedError()

    def _write_card_bytes(self, card: CardConnection, page: int, message: bytes):
        raise NotImplementedError()

class ACR122U(Reader):

    success_sw: tuple[int, int] = (0x90, 0x00)
    read_apdu: list[int] = [0xFF, 0xB0, 0x00] # + [page, amount_of_bytes_to_read]
    write_apdu: list[int] = [0xFF, 0xD6, 0x00] # + [page, amount_of_bytes_to_write] + content

    def __init__(self, tag: Tag, verbose: bool = False, timeout_sec: int = 3600):
        max_bytes_per_read = 16
        super().__init__(tag, max_bytes_per_read, verbose, timeout_sec)

    def _read_card_bytes(self, card: CardConnection, page: int, length_in_bytes: int) -> bytes:
        read_amount = ceil(length_in_bytes / self.max_bytes_per_read) # The number of reads APDU that needs to be done
        length_in_pages = ceil(length_in_bytes / self.tag.bytes_per_page)
        end_page = page + length_in_pages
        if end_page > self.tag.memory_page_max:
            pages_over_limit = self.tag.memory_page_max - end_page
            bytes_over_limit = pages_over_limit * self.tag.bytes_per_page
            self._log(f"Trying to read {pages_over_limit} page(s) ({bytes_over_limit} bytes) past the card memory limit.")
            length_in_bytes -= int(bytes_over_limit)

        pages_per_read = self.max_bytes_per_read // self.tag.bytes_per_page
        data = bytearray()
        for _ in range(read_amount):
            if page < self.tag.memory_page_start:
                self._log(f"WARNING ! You're reading outside of user memory. Reading page {page}: User memory starts at {self.tag.memory_page_start}")

            self._log(f"Sending APDU for reading {self.max_bytes_per_read} bytes at page {page}")
            apdu = self.read_apdu + [page, self.max_bytes_per_read]
            try:
                new_data, sw1, sw2 = card.transmit(apdu)
            except CardConnectionException as err:
                if page == self.tag.memory_page_start:
                    print("Card has no content.")
                self._log(f"An error occured when sending the read APDU: {err}")
                break
            if (sw1, sw2) != self.success_sw:
                raise CardConnectionException(f"Failed to read {length_in_bytes} bytes at page {page}. SW: {hex(sw1)} {hex(sw2)}")
            data.extend(new_data)
            page += pages_per_read
        return bytes(data)

    def _write_card_bytes(self, card: CardConnection, page: int, message: bytes):
        message_size = len(message)
        bytes_per_write = self.tag.bytes_per_page
        self._log(f"Writing {message_size} bytes to page {page}...")
        for byte_index in range(0, message_size, bytes_per_write):
            content = message[byte_index : byte_index + bytes_per_write]
            current_page = page + (byte_index // bytes_per_write)
            apdu = self.write_apdu + [current_page, bytes_per_write] + list(content)
            self._log("Sending APDU for writing {bytes_per_write} bytes at page {current_page}")
            _, sw1, sw2 = card.transmit(apdu)

            if (sw1, sw2) != self.success_sw:
                raise CardConnectionException(f"Failed to write {bytes_per_write} bytes at page {current_page}. SW: {hex(sw1)} {hex(sw2)}")
