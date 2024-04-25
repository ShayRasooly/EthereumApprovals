import argparse
import json
from urllib.request import urlopen
from hexbytes import HexBytes
from web3 import Web3

ABI_JSON_URL = 'https://gist.githubusercontent.com/veox/8800debbf56e24718f9f483e1e40c35c/raw/f853187315486225002ba56e5283c1dba0556e6f/erc20.abi.json'
with urlopen(ABI_JSON_URL) as json_file:
    ABI = json.load(json_file)
API_KEY = "****"
APPROVAL_SIGNATURE = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"


def parse_args():
    parser = argparse.ArgumentParser(description='Ethereum Approvals')
    parser.add_argument('-a', '--address', help='owner address of which all the approvals should be listed',
                        required=True)
    parser.add_argument('-b', '--block', help='specific block index to list', required=False)
    parser.add_argument('-f', '--fromBlock', help='specific block index to list from', required=False)
    parser.add_argument('-t', '--toBlock', help='specific block index to list from', required=False)
    return vars(parser.parse_args())


def get_filter_dict(args):
    filter_dict = {"topics": [APPROVAL_SIGNATURE]}
    if args['block']:
        filter_dict["fromBlock"] = filter_dict["toBlock"] = hex(int(args['block']))
    else:
        if args['fromBlock']:
            filter_dict["fromBlock"] = hex(int(args['fromBlock']))
        if args['toBlock']:
            filter_dict["toBlock"] = hex(int(args['toBlock']))
    return filter_dict


def get_owner_address(event_log):
    return event_log["topics"][1]

def get_token(w3, event_log):
    contract = w3.eth.contract(address=event_log["address"], abi=ABI)
    return contract.functions.name().call()



def main(args):
    url = f'https://mainnet.infura.io/v3/{API_KEY}'
    w3 = Web3(Web3.HTTPProvider(url))
    owner_address = HexBytes(args["address"])

    approvals_log_entries = w3.eth.filter(get_filter_dict(args)).get_all_entries()

    for log_entry in approvals_log_entries:
        if owner_address == get_owner_address(log_entry):
            amount = int.from_bytes(log_entry["data"])
            token = get_token(w3, log_entry)
            print(f"approval on {token} on amount of {amount}")

if __name__ == "__main__":
    args = parse_args()
    main(args)
