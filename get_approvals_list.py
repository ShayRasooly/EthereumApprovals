import argparse
import json
from hexbytes import HexBytes
from web3 import Web3
import requests
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
    parser.add_argument('-c', '--currency', help='show price of the token in a specific currency, in 3-4 characters',
                        required=False)
    parser.add_argument('-e', '--exposureCurrency',
                        help='choose the currency to show exposure in (enabled onlly if arg "currency" exist, '
                             'default is usd',
                        required=False, default='usd')
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


def get_spender_address(event_log):
    return event_log["topics"][2]


def get_token(w3, event_log):
    contract = w3.eth.contract(address=event_log["address"], abi=ABI)
    return contract.functions.name().call()


def get_token_rate(token, currency):
    if (token, currency) in get_token_rate.rates:
        return get_token_rate.rates[(token, currency)]

    url = 'https://api.coingecko.com/api/v3/simple/price'
    params = {
        'ids': token,
        'vs_currencies': currency
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        response = response.json()
        if response:
            get_token_rate.rates[(token, currency)] = response[token][currency]
            return response[token][currency]


# cache to avoid too many unnecessary api calls
get_token_rate.rates = {}


def get_addresses(address):
    PREFIX = "0x"
    SHORT_LEN_BYTES = 20
    LONG_LEN_BYTES = 32
    prefix_len = len(PREFIX)
    short_len_chars = SHORT_LEN_BYTES * 2
    long_len_chars = LONG_LEN_BYTES * 2
    short_len_str = short_len_chars + prefix_len
    long_len_str = long_len_chars + prefix_len
    if len(address) == short_len_str:
        short_address = address
        zeros = (long_len_chars - (len(address) - prefix_len)) * '0'
        long_address = PREFIX + zeros + address[prefix_len:]
    elif len(address) == long_len_str:
        long_address = address
        short_address = "0x" + address[-short_len_chars:]
    else:
        print("wrong address length")
        return
    return HexBytes(short_address), HexBytes(long_address)


def get_balance_in_currency(w3, address, currency):
    WEI_TO_ETH = 10 ** 18
    balance_in_wei = w3.eth.get_balance(address)
    eth_rate = get_token_rate("ethereum", currency)
    return (balance_in_wei * eth_rate) / WEI_TO_ETH


def get_exposure(amount, balance):
    return min(amount, balance)


def get_approvals_list_by_address(args):
    url = f'https://mainnet.infura.io/v3/{API_KEY}'
    w3 = Web3(Web3.HTTPProvider(url))
    filter_dict = get_filter_dict_from_args(args)
    approvals_log_entries = w3.eth.filter(filter_dict).get_all_entries()
    currency = args["currency"]
    approvals_by_spender_and_token = {}
    exp_cur = args["exposureCurrency"]
    balance = get_balance_in_currency(w3, args["short_address"], exp_cur)

    for log_entry in approvals_log_entries:
        if args["long_address"] != get_owner_address(log_entry):
            continue
        spender = get_spender_address(log_entry)
        token = get_token(w3, log_entry)
        if (spender, token) in approvals_by_spender_and_token:
            other_approval = approvals_by_spender_and_token[(spender, token)]
            if log_entry["blockNumber"] == other_approval["blockNumber"]:
                if log_entry["logIndex"] < other_approval["logIndex"]:
                    continue
            elif log_entry["blockNumber"] < other_approval["blockNumber"]:
                continue
        amount = int.from_bytes(log_entry["data"])
        entry_str = f"approval on {token} on amount of {amount}"
        if currency:
            rate = get_token_rate(token.lower(), currency.lower())
            exp_cur_rate = get_token_rate(token.lower(), exp_cur.lower())
            if rate and exp_cur_rate:
                entry_str += f"\nThe rate of {token} is {rate} {currency}. the approval is on the amount of {rate * amount} {currency}"
                amount_in_exp_cur = exp_cur_rate * amount
                exposure = get_exposure(amount_in_exp_cur, balance)
                entry_str += (f"\nThe rate of {token} in exposure currency is {exp_cur_rate} {exp_cur}. the approval "
                              f"is on the amount of {amount_in_exp_cur} {exp_cur}, the balance is {balance} {
                              exp_cur}, therefore the exposure is {exposure} {exp_cur}")

            else:
                entry_str += f"\nThe rate of {token} is not available in {currency}"
                entry_str += f"\ncant calculate exposure. the balance is {balance} {exp_cur}"
        approvals_by_spender_and_token[(spender, token)] = {"blockNumber": log_entry["blockNumber"],
                                                            "logIndex": log_entry["logIndex"], "entry_str": entry_str}

    return [entry["entry_str"] for entry in approvals_by_spender_and_token.values()]


@app.get('/approvals/{address}')
async def get_approvals_list(address: str, block: str | None = None, from_block: str | None = None,
                             to_block: str | None = None, currency: str | None = None, exposure_currency: str = 'usd'):
    args = {"block": block, "fromBlock": from_block, "toBlock": to_block, "currency": currency,
            "exposureCurrency": exposure_currency}
    args["short_address"], args["long_address"] = get_addresses(address)
    approvals = get_approvals_list_by_address(args)
    return {i: approval for i, approval in enumerate(approvals)}


def print_approvals(args):
    args["short_address"], args["long_address"] = get_addresses(args["address"])
    approvals = get_approvals_list_by_address(args)
    for approval in approvals:
        print(approval)


if __name__ == "__main__":
    args = parse_args()
    if args["server"]:
        uvicorn.run("get_approvals_list:app", host="127.0.0.1", port=8000, reload=True, access_log=False)
    print_approvals(args)

0x0000000000000000000000000000000000000000005e20fcf757b55d6e27dea9ba4f90c0b03ef852
0x000000000000000000000000005e20fCf757B55D6E27dEA9BA4f90C0B03ef852
