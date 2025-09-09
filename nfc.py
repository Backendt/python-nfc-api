#!/usr/bin/env python3

from argparse import ArgumentParser
from ndef import message_decoder, Record
from smartcard.Exceptions import CardRequestException

from tag import NTAG216
from reader import Reader, ACR122U

class Contact:
    name: str
    phone: str
    email: str
    company: str

    def __init__(self, name: str, phone: str, email: str, company: str):
        self.name = name.strip()
        self.phone = phone.strip()
        self.email = email.strip()
        self.company = company.strip()

    def __str__(self) -> str:
        return f"""
Name: {self.name}
Phone: {self.phone}
Email: {self.email}
Company: {self.company}
"""

    def check(self):
        if len(self.name.strip()) < 3:
            raise ValueError("The name is too short.")
        phone_length = len(self.phone.strip())
        if phone_length != 10 or not (phone_length == 13 and self.phone.startswith('+')):
            raise ValueError("Invalid phone number.")
        if "@" not in self.email:
            raise ValueError("Invalid email.")
        if len(self.company.strip()) < 1:
            raise ValueError("Company is required.")

    def as_vcard(self) -> str:
        return f"""BEGING:VCARD
VERSION:3.0
FN:{self.name}
ORG:{self.company}
TEL:{self.phone}
EMAIL:{self.email}
END:VCARD
"""

    @staticmethod
    def from_vcard(vcard: str):
        contact = Contact("Unknown", "Unknown", "0000000000", "Unknown")
        for line in vcard.splitlines():
            key, value = line.split(":", 1)
            match key:
                case "FN":
                    contact.name = value
                case "ORG":
                    contact.company = value
                case "TEL":
                    contact.phone = value
                case "EMAIL":
                    contact.email = value
        return contact

    @staticmethod
    def create_interactively():
        name = input("Enter full name: ")
        phone = input("Enter phone: ")
        email = input("Enter email: ")
        company = input("Enter company: ")
        return Contact(name, phone, email, company)
        
class VCardAPI:
    verbose: bool
    reader: Reader

    def __init__(self, reader: Reader, verbose: bool = False):
        self.verbose = verbose
        self.reader = reader

    def _log(self, message: str):
        if self.verbose:
            print(message)

    def read_contact(self) -> Contact:
        card_bytes = self.reader.wait_for_card(self.reader.read_card)
        if not card_bytes:
            raise ValueError("Could not read contact from card")
        if not isinstance(card_bytes, bytes):
            raise ValueError("Unexpected body type from card: ", card_bytes)
        records = message_decoder(card_bytes)
        for record in records:
            if not isinstance(record, Record):
                continue
            record_type = record.type if isinstance(record.type, str) else record.type.decode("ascii", errors="ignore")
            if record_type not in ["text/vcard", "text/x-vcard"]:
                self._log(f"Ignoring record of type: {record_type}")
                continue
            vcard = record.data.decode("utf-8", errors="replace")
            return Contact.from_vcard(vcard)
        raise CardRequestException("The card does not contain any vcard.")

    def write_contact(self, contact: Contact):
        vcard = contact.as_vcard()
        self._log("Writing contact..")
        self.reader.wait_for_card(self.reader.write_card, "text/x-vcard", vcard.encode("utf-8"))
        self._log("Contact written")

def _get_args():
    parser = ArgumentParser()
    parser.add_argument("-w", "--write", required=False, action="store_true")
    parser.add_argument("-v", "--verbose", required=False, action="store_true")
    parser.add_argument("-t", "--timeout", required=False, type=int, default=10, help="The maximum time in seconds to wait for a card")

    return parser.parse_args()

def _main():
    args = _get_args()
    tag = ACR122U(NTAG216, args.verbose, args.timeout)
    reader = VCardAPI(tag, args.verbose)
    if args.write:
        contact = Contact.create_interactively()
        reader.write_contact(contact)
    else:
        contact = reader.read_contact()
        print(contact)

if __name__ == "__main__":
    _main()
