#
# Copyright (C) 2014 Red Hat, Inc
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import json
import unittest

from gerrymander.model import ModelChange, ModelUser, ModelPatch, ModelApproval

JSON_CHANGE='''
{
    "project": "openstack/nova-specs",
    "branch": "master",
    "topic": "bp/is",
    "id": "Idcf7b35c93422d0d13c3ffb33aca3c5eca4f3c94",
    "number": "85556",
    "subject": "Libvirt-Enable suppport for discard option for disk device",
    "owner": {
        "name": "boh.ricky",
        "email": "boh.ricky@gmail.com",
        "username": "boh.ricky"
    },
    "url": "https://review.openstack.org/85556",
    "createdOn": 1396715237,
    "lastUpdated": 1397487650,
    "sortKey": "002c6ba400014e34",
    "open": true,
    "status": "NEW",
    "patchSets": [
        {
            "number": "1",
            "revision": "b2bc7a9f5feab51b61fc9c7725251868e998703d",
            "ref": "refs/changes/56/85556/1",
            "uploader": {
                "name": "boh.ricky",
                "email": "boh.ricky@gmail.com",
                "username": "boh.ricky"
            },
            "createdOn": 1396715237,
            "approvals": [
                {
                    "type": "Verified",
                    "description": "Verified",
                    "value": "-1",
                    "grantedOn": 1396715281,
                    "by": {
                        "name": "Jenkins",
                        "username": "jenkins"
                    }
                }
            ]
        },
        {
            "number": "2",
            "revision": "1ea93fd986afabc479bf93a4ce0c6df4924a7c9e",
            "ref": "refs/changes/56/85556/2",
            "uploader": {
                "name": "boh.ricky",
                "email": "boh.ricky@gmail.com",
                "username": "boh.ricky"
            },
            "createdOn": 1396716807,
            "approvals": [
                {
                    "type": "Verified",
                    "description": "Verified",
                    "value": "1",
                    "grantedOn": 1397487649,
                    "by": {
                        "name": "Jenkins",
                        "username": "jenkins"
                    }
                },
                {
                    "type": "CRVW",
                    "description": "Code Review",
                    "value": "-1",
                    "grantedOn": 1397040232,
                    "by": {
                        "name": "Daniel Berrange",
                        "email": "berrange@redhat.com",
                        "username": "berrange"
                    }
                },
                {
                    "type": "CRVW",
                    "description": "Code Review",
                    "value": "-1",
                    "grantedOn": 1397137466,
                    "by": {
                        "name": "Dan Smith",
                        "email": "dms@danplanet.com",
                        "username": "danms"
                    }
                }
            ]
        }
    ]
}'''

class TestGerrymanderModel(unittest.TestCase):

    def test_json_parse(self):
        change = ModelChange.from_json(json.loads(JSON_CHANGE))

        self.assertEqual(type(change), ModelChange)

        self.assertEqual(change.project, "openstack/nova-specs")
        self.assertEqual(change.branch, "master")
        self.assertEqual(change.number, 85556)
        self.assertEqual(change.subject, "Libvirt-Enable suppport for discard option for disk device")
        self.assertEqual(change.url, "https://review.openstack.org/85556")
        self.assertEqual(change.createdOn, 1396715237)
        self.assertEqual(change.lastUpdated, 1397487650)
        self.assertEqual(change.status, "NEW")

        self.assertEqual(type(change.owner), ModelUser)
        self.assertEqual(change.owner.name, "boh.ricky")
        self.assertEqual(change.owner.username, "boh.ricky")
        self.assertEqual(change.owner.email, "boh.ricky@gmail.com")

        self.assertEqual(len(change.patches), 2)
        self.assertEqual(change.patches[0].number, 1)
        self.assertEqual(change.patches[0].revision, "b2bc7a9f5feab51b61fc9c7725251868e998703d")
        self.assertEqual(change.patches[0].ref, "refs/changes/56/85556/1")
        self.assertEqual(change.patches[0].createdOn, 1396715237)

        self.assertEqual(type(change.patches[0].uploader), ModelUser)
        self.assertEqual(change.patches[0].uploader.name, "boh.ricky")
        self.assertEqual(change.patches[0].uploader.username, "boh.ricky")
        self.assertEqual(change.patches[0].uploader.email, "boh.ricky@gmail.com")

        self.assertEqual(len(change.patches[0].approvals), 1)
        self.assertEqual(type(change.patches[0].approvals[0]), ModelApproval)
        self.assertEqual(change.patches[0].approvals[0].action, ModelApproval.ACTION_VERIFIED)
        self.assertEqual(change.patches[0].approvals[0].description, "Verified")
        self.assertEqual(change.patches[0].approvals[0].value, -1)
        self.assertEqual(change.patches[0].approvals[0].grantedOn, 1396715281)

        self.assertEqual(type(change.patches[0].approvals[0].user), ModelUser)
        self.assertEqual(change.patches[0].approvals[0].user.name, "Jenkins")
        self.assertEqual(change.patches[0].approvals[0].user.username, "jenkins")
