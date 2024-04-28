import argparse
import json
from hexbytes import HexBytes
from web3 import Web3

import uvicorn
from fastapi import FastAPI

# ABI_JSON_URL = 'https://gist.githubusercontent.com/veox/8800debbf56e24718f9f483e1e40c35c/raw
# /f853187315486225002ba56e5283c1dba0556e6f/erc20.abi.json'
# from urllib.request import urlopen with urlopen(ABI_JSON_URL) as json_file: ABI = json.load(json_file)
# fetching from url is io heavy, copying and reading from  local file instead
with open("abi.json") as f:
    ABI = json.load(f)
with open("api_key.txt") as f:
    API_KEY = f.read()
APPROVAL_SIGNATURE = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
app = FastAPI()


def parse_args():
    parser = argparse.ArgumentParser(description='Ethereum Approvals')
    parser.add_argument('-s', '--server', help='start server mode, ignore all other arguments', action='store_true')
    parser.add_argument('-a', '--address', help='owner address of which all the approvals should be listed',
                        required=False)
    parser.add_argument('-b', '--block', help='specific block index to list', required=False)
    parser.add_argument('-f', '--fromBlock', help='specific block index to list from', required=False)
    parser.add_argument('-t', '--toBlock', help='specific block index to list from', required=False)
    return vars(parser.parse_args())


def get_default_filter_dict():
    return {"topics": [APPROVAL_SIGNATURE]}


def get_filter_dict_from_args(args):
    filter_dict = get_default_filter_dict()
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


def get_approvals_list_by_address(args):
    url = f'https://mainnet.infura.io/v3/{API_KEY}'
    w3 = Web3(Web3.HTTPProvider(url))
    filter_dict = get_filter_dict_from_args(args)
    approvals_log_entries = w3.eth.filter(filter_dict).get_all_entries()
    out_list = []

    for log_entry in approvals_log_entries:
        if args["address"] == get_owner_address(log_entry):
            amount = int.from_bytes(log_entry["data"])
            token = get_token(w3, log_entry)
            out_list.append(f"approval on {token} on amount of {amount}")
    return out_list


@app.get('/approvals/{owner_address}')
async def get_approvals_list(owner_address: str, block: str | None = None, fromBlock: str | None = None,
                             toBlock: str | None = None):
    args = {"address": HexBytes(owner_address), "block": block, "fromBlock": fromBlock, "toBlock": toBlock}
    approvals = get_approvals_list_by_address(args)
    return {i: approval for i, approval in enumerate(approvals)}


def print_approvals(args):
    args["address"] = HexBytes(args["address"])
    approvals = get_approvals_list_by_address(args)
    for approval in approvals:
        print(approval)


if __name__ == "__main__":
    args = parse_args()
    if args["server"]:
        uvicorn.run("get_approvals_list:app", host="127.0.0.1", port=8000, reload=True, access_log=False)
    print_approvals(args)
