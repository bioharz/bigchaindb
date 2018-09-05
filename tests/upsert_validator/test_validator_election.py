# Copyright BigchainDB GmbH and BigchainDB contributors
# SPDX-License-Identifier: (Apache-2.0 AND CC-BY-4.0)
# Code is Apache-2.0 and docs are CC-BY-4.0
from argparse import Namespace

import pytest

from bigchaindb.tendermint_utils import public_key_to_base64
from bigchaindb.upsert_validator import ValidatorElection
from bigchaindb.common.exceptions import (DuplicateTransaction,
                                          UnequalValidatorSet,
                                          InvalidProposer,
                                          MultipleInputsError,
                                          InvalidPowerChange)

pytestmark = [pytest.mark.tendermint, pytest.mark.bdb]


def test_upsert_validator_valid_election(b_mock, new_validator, node_key):
    voters = ValidatorElection.recipients(b_mock)
    election = ValidatorElection.generate([node_key.public_key],
                                          voters,
                                          new_validator, None).sign([node_key.private_key])
    assert election.validate(b_mock)


def test_upsert_validator_invalid_power_election(b_mock, new_validator, node_key):
    voters = ValidatorElection.recipients(b_mock)
    new_validator['power'] = 30

    election = ValidatorElection.generate([node_key.public_key],
                                          voters,
                                          new_validator, None).sign([node_key.private_key])
    with pytest.raises(InvalidPowerChange):
        election.validate(b_mock)


def test_upsert_validator_invalid_proposed_election(b_mock, new_validator, node_key):
    from bigchaindb.common.crypto import generate_key_pair

    alice = generate_key_pair()
    voters = ValidatorElection.recipients(b_mock)
    election = ValidatorElection.generate([alice.public_key],
                                          voters,
                                          new_validator, None).sign([alice.private_key])
    with pytest.raises(InvalidProposer):
        election.validate(b_mock)


def test_upsert_validator_invalid_inputs_election(b_mock, new_validator, node_key):
    from bigchaindb.common.crypto import generate_key_pair

    alice = generate_key_pair()
    voters = ValidatorElection.recipients(b_mock)
    election = ValidatorElection.generate([node_key.public_key, alice.public_key],
                                          voters,
                                          new_validator, None).sign([node_key.private_key, alice.private_key])
    with pytest.raises(MultipleInputsError):
        election.validate(b_mock)


def test_upsert_validator_invalid_election(b_mock, new_validator, node_key, valid_election):
    voters = ValidatorElection.recipients(b_mock)
    duplicate_election = ValidatorElection.generate([node_key.public_key],
                                                    voters,
                                                    new_validator, None).sign([node_key.private_key])

    with pytest.raises(DuplicateTransaction):
        valid_election.validate(b_mock, [duplicate_election])

    b_mock.store_bulk_transactions([valid_election])

    with pytest.raises(DuplicateTransaction):
        duplicate_election.validate(b_mock)

    # Try creating an election with incomplete voter set
    invalid_election = ValidatorElection.generate([node_key.public_key],
                                                  voters[1:],
                                                  new_validator, None).sign([node_key.private_key])

    with pytest.raises(UnequalValidatorSet):
        invalid_election.validate(b_mock)

    recipients = ValidatorElection.recipients(b_mock)
    altered_recipients = []
    for r in recipients:
        ([r_public_key], voting_power) = r
        altered_recipients.append(([r_public_key], voting_power - 1))

    # Create a transaction which doesn't enfore the network power
    tx_election = ValidatorElection.generate([node_key.public_key],
                                             altered_recipients,
                                             new_validator, None).sign([node_key.private_key])

    with pytest.raises(UnequalValidatorSet):
        tx_election.validate(b_mock)


def test_get_status_ongoing(b, ongoing_election, new_validator):
    status = ValidatorElection.ONGOING
    resp = ongoing_election.get_status(b)
    assert resp == status


def test_get_status_concluded(b, concluded_election, new_validator):
    status = ValidatorElection.CONCLUDED
    resp = concluded_election.get_status(b)
    assert resp == status


def test_get_status_inconclusive(b, inconclusive_election, new_validator):
    def custom_mock_get_validators(height):
        if height >= 3:
            return [{'pub_key': {'data': 'zL/DasvKulXZzhSNFwx4cLRXKkSM9GPK7Y0nZ4FEylM=',
                                 'type': 'AC26791624DE60'},
                     'voting_power': 15},
                    {'pub_key': {'data': 'GIijU7GBcVyiVUcB0GwWZbxCxdk2xV6pxdvL24s/AqM=',
                                 'type': 'AC26791624DE60'},
                     'voting_power': 7},
                    {'pub_key': {'data': 'JbfwrLvCVIwOPm8tj8936ki7IYbmGHjPiKb6nAZegRA=',
                                 'type': 'AC26791624DE60'},
                     'voting_power': 10},
                    {'pub_key': {'data': 'PecJ58SaNRsWJZodDmqjpCWqG6btdwXFHLyE40RYlYM=',
                                 'type': 'AC26791624DE60'},
                     'voting_power': 8}]
        else:
            return [{'pub_key': {'data': 'zL/DasvKulXZzhSNFwx4cLRXKkSM9GPK7Y0nZ4FEylM=',
                                 'type': 'AC26791624DE60'},
                     'voting_power': 9},
                    {'pub_key': {'data': 'GIijU7GBcVyiVUcB0GwWZbxCxdk2xV6pxdvL24s/AqM=',
                                 'type': 'AC26791624DE60'},
                     'voting_power': 7},
                    {'pub_key': {'data': 'JbfwrLvCVIwOPm8tj8936ki7IYbmGHjPiKb6nAZegRA=',
                                 'type': 'AC26791624DE60'},
                     'voting_power': 10},
                    {'pub_key': {'data': 'PecJ58SaNRsWJZodDmqjpCWqG6btdwXFHLyE40RYlYM=',
                                 'type': 'AC26791624DE60'},
                     'voting_power': 8}]

    b.get_validators = custom_mock_get_validators
    status = ValidatorElection.INCONCLUSIVE
    resp = inconclusive_election.get_status(b)
    assert resp == status


def test_upsert_validator_show(caplog, ongoing_election, b):
    from bigchaindb.commands.bigchaindb import run_upsert_validator_show

    election_id = ongoing_election.id
    public_key = public_key_to_base64(ongoing_election.asset['data']['public_key'])
    power = ongoing_election.asset['data']['power']
    node_id = ongoing_election.asset['data']['node_id']
    status = ValidatorElection.ONGOING

    show_args = Namespace(action='show',
                          election_id=election_id)

    msg = run_upsert_validator_show(show_args, b)

    assert msg == f'public_key={public_key}\npower={power}\nnode_id={node_id}\nstatus={status}'