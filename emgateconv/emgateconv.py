#!/usr/bin/env python3
# -*- coding: utf-8, vim: expandtab:ts=4 -*-

from json import loads as json_loads
from bs4 import BeautifulSoup


class EmGATEConv:
    pass_header = False

    def __init__(self, source_fields=None, target_fields=None):
        """
        The initialisation of the module. One can extend the lsit of parameters as needed. The mandatory fields which
         should be set by keywords are the following:
        :param source_fields: the set of names of the input fields
        :param target_fields: the list of names of the output fields in generation order
        """
        # Custom code goes here

        # Field names for xtsv (the code below is mandatory for an xtsv module)
        if source_fields is None:
            source_fields = set()

        if target_fields is None:
            target_fields = []

        self.source_fields = source_fields
        self.target_fields = target_fields

        self._skeleton = """<?xml version="1.0" encoding="UTF-8" ?>
        <GateDocument>
        <!-- The document's features-->

        <GateDocumentFeatures>
        <Feature>
          <Name className="java.lang.String">gate.SourceURL</Name>
          <Value className="java.lang.String">created from String</Value>
        </Feature>
        </GateDocumentFeatures>
        <!-- The document content area with serialized nodes -->

        <TextWithNodes></TextWithNodes>
        <!-- The default annotation set -->

        <AnnotationSet>
        </AnnotationSet>
        </GateDocument>
        """

        self._bs_obj = BeautifulSoup(' ', 'lxml-xml')
        self._class_name_to_name = {'length': {'className': 'java.lang.Long'},
                                    'depTarget': {'className': 'java.lang.Integer'},
                                    'anas': {'className': 'java.util.ArrayList', 'itemClassName': 'java.lang.String'},
                                    'childIds': {'className': 'java.util.ArrayList',
                                                 'itemClassName': 'java.lang.String'},
                                    'other': {'className': 'java.lang.String'},
                                    }
        self._emtsv_to_gate_header = {'anas': 'anas', 'lemma': 'lemma', 'xpostag': 'hfstana', 'feats': 'feature',
                                      'upostag': 'pos',
                                      'NP-BIO': 'NP-BIO', 'NER-BIO': 'NER-BIO1', 'deprel': 'depType',
                                      'head': 'depTarget', 'cons': 'cons'}
        self._gid = 0
        self._aid = 0
        self._text = []
        self._xml = BeautifulSoup(self._skeleton, 'lxml-xml')
        self._text_with_nodes = self._xml.find('TextWithNodes')
        self._annotation_set = self._xml.find('AnnotationSet')

    def process_sentence(self, sen, field_names):
        sent_start = self._gid
        nps = []
        nes = []
        for tok in sen:
            feat_tags = [self._create_feature(gate_featname, tok[field_names[feat]])
                         for feat, gate_featname in self._emtsv_to_gate_header.items()
                         if feat in field_names.keys()]
            np_bio_index = field_names.get('NP-BIO')
            if np_bio_index is not None:
                np_bio = tok[np_bio_index]
                if np_bio != 'O':
                    self._handle_bio(nps, self._gid, self._aid, np_bio)

            ne_bio_index = field_names.get('NER-BIO')
            if ne_bio_index is not None:
                ne_bio = tok[ne_bio_index]
                if ne_bio != 'O':
                    self._handle_bio(nes, self._gid, self._aid, ne_bio)

            form = tok[field_names['form']]
            new_tok = self._create_annot(form, self._aid, self._gid, feat_tags)
            self._annotation_set.append(new_tok)
            self._text.append(form)
            self._aid += 1
            self._gid += 1

            # WSpace handling
            ws_after = tok[field_names['wsafter']]
            if len(ws_after) > 2:
                wsafter_value = ws_after[1:-1]
                new_tok = self._create_annot(wsafter_value, self._aid, self._gid, [], tok_type='SpaceToken')
                self._annotation_set.append(new_tok)
                self._text.append(wsafter_value)
                self._aid += 1
                self._gid += 1
        else:
            new_sent = self._create_annot(''.join(self._text[sent_start:self._gid + 1]), self._aid, sent_start, [],
                                          tok_type='Sentence', end_gid=self._gid)
            self._annotation_set.append(new_sent)
            self._aid += 1
            self._put_entitiy_annot('NP', self._aid, self._annotation_set, nps, self._text)
            self._aid += len(nps)
            self._put_entitiy_annot('NE', self._aid, self._annotation_set, nes, self._text)
            self._aid += len(nes)

        return []  # Finaliser!

    @staticmethod
    def prepare_fields(field_names):
        return field_names

    def final_output(self):
        nodes = [self._bs_obj.new_tag('Node', attrs={'id': 0})]
        for i, text_elem in enumerate(self._text, start=1):
            nodes.append(text_elem)
            nodes.append(self._bs_obj.new_tag('Node', attrs={'id': i}))
        self._text_with_nodes.extend(nodes)
        yield from self._xml.prettify()

    @staticmethod
    def _reformat_anas(ana):
        """
             {ana=az[/Det|Pro]=az+[Nom], feats=[/Det|Pro][Nom], lemma=az, readable_ana=az[/Det|Pro] + [Nom]};
             {ana=az[/Det|art.Def]=az, feats=[/Det|art.Def], lemma=az, readable_ana=az[/Det|art.Def]};
             {ana=az[/N|Pro]=az+[Nom], feats=[/N|Pro][Nom], lemma=az, readable_ana=az[/N|Pro] + [Nom]}
        """
        out = []
        for anal in json_loads(ana):
            out.append('{{{0}}}'.format(', '.join(f'{elem_gate_key}={anal[elem_key]}'
                                                  for elem_key, elem_gate_key in
                                                  (('morphana', 'ana'), ('tag', 'feats'), ('lemma', 'lemma'),
                                                   ('readable', 'readable_ana')))))
        return ';'.join(out)

    def _create_feature(self, name, value):
        """
        Output e.g.:
        <Feature>
            <Name className="java.lang.String">kind</Name>
            <Value className="java.lang.String">word</Value>
        </Feature>
        """

        feat_tag = self._bs_obj.new_tag('Feature')
        name_tag = self._bs_obj.new_tag('Name', className='java.lang.String')
        name_tag.string = str(name)
        feat_tag.append(name_tag)
        value_tag = self._bs_obj.new_tag('Value', attrs=self._class_name_to_name.get(name,
                                                                                     self._class_name_to_name['other']))
        if name == 'anas':
            value = self._reformat_anas(value)
        value_tag.string = str(value)
        feat_tag.append(value_tag)
        return feat_tag

    def _create_annot(self, tok_field, annot_id, global_id, features, tok_type='Token', end_gid=None):
        if end_gid is None:
            end_gid = global_id + 1
        tok_field_len = len(tok_field)

        new_tok_tag = self._bs_obj.new_tag('Annotation', attrs={'Id': str(annot_id), 'Type': tok_type,
                                                                'StartNode': str(global_id), 'EndNode': str(end_gid)})
        if len(features) > 0:
            new_tok_tag.extend(features)
        if tok_type not in {'NE', 'NP'}:
            new_tok_tag.append(self._create_feature('string', tok_field))
            new_tok_tag.append(self._create_feature('length', tok_field_len))
        else:
            new_tok_tag.append(self._create_feature('text', tok_field))
        if tok_type == 'Token':
            new_tok_tag.append(self._create_feature('kind', 'word'))

        return new_tok_tag

    @staticmethod
    def _handle_bio(elems, global_id, annotation_id, bio):
        if bio.startswith(('B', '1', 'S')):
            elems.append([[global_id], [str(annotation_id)]])
        elif bio.startswith(('I', 'E')):
            elems[-1][0].append(global_id)
            elems[-1][1].append(str(annotation_id))
        else:
            raise ValueError(f'Unknown state: {bio}')

    def _put_entitiy_annot(self, ent_type, aid, annot_set, entities, text):
        for glob_ids, annot_ids in entities:
            start = glob_ids[0]
            end = glob_ids[-1]
            new_ent = self._create_annot(''.join(text[start:end + 1]), aid, start,
                                         [self._create_feature('childIds', ';'.join(annot_ids))],
                                         tok_type=ent_type, end_gid=end)
            annot_set.append(new_ent)
            aid += 1
