import unittest
from copy import deepcopy
from aipictures.workflow import ImageRequest, build_workflow
from aipictures.prompt_binding import bind_request, bindings


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.request = ImageRequest('sdxl', 'a small red robot', 'blurry', width=512, height=640,
                                    seed=8123, steps=12)
        self.template = build_workflow(ImageRequest('sdxl', 'original prompt', 'original negative'))

    def test_request_binds_conditioning_without_mutating_template(self):
        original = deepcopy(self.template)
        graph, mapping = bind_request(self.template, self.request)
        self.assertEqual(graph['2']['inputs']['text'], self.request.positive)
        self.assertEqual(graph['3']['inputs']['text'], self.request.negative)
        self.assertEqual(graph['5']['inputs']['steps'], 12)
        self.assertEqual(self.template, original)
        self.assertEqual(mapping['positive'], [('2', 'text')])

    def test_reference_inserts_real_img2img_path(self):
        graph, mapping = bind_request(self.template, self.request, 'AIPictures/ref.png', .55)
        self.assertEqual(graph[mapping['reference'][0]]['inputs']['image'], 'AIPictures/ref.png')
        encoder = graph[graph['5']['inputs']['latent_image'][0]]
        self.assertEqual(encoder['class_type'], 'VAEEncode')
        self.assertEqual(encoder['inputs']['vae'], ['1', 2])
        self.assertEqual(graph['5']['inputs']['denoise'], .55)

    def test_identity_reference_does_not_replace_pose_image(self):
        graph = deepcopy(self.template)
        graph['10'] = {'class_type': 'LoadImage', 'inputs': {'image': 'character.png'}}
        graph['14'] = {'class_type': 'LoadImage', 'inputs': {'image': 'pose.png'}}
        graph['12'] = {'class_type': 'IPAdapterAdvanced', 'inputs': {'image': ['10', 0]}}
        graph['16'] = {'class_type': 'ControlNetApplyAdvanced', 'inputs': {
            'positive': ['2', 0], 'negative': ['3', 0], 'image': ['14', 0]}}
        graph['5']['inputs'].update(positive=['16', 0], negative=['16', 1])
        bound, mapping = bind_request(graph, self.request, 'new_reference.png')
        self.assertEqual(mapping['reference'], ['10'])
        self.assertEqual(bound['10']['inputs']['image'], 'new_reference.png')
        self.assertEqual(bound['14']['inputs']['image'], 'pose.png')
        self.assertEqual(bound['2']['inputs']['text'], self.request.positive)
        self.assertEqual(bound['3']['inputs']['text'], self.request.negative)

    def test_ambiguous_prompts_are_rejected(self):
        graph = deepcopy(self.template)
        graph['20'] = deepcopy(graph['2'])
        graph['21'] = {'class_type': 'ConditioningCombine', 'inputs': {
            'conditioning_1': ['2', 0], 'conditioning_2': ['20', 0]}}
        graph['5']['inputs']['positive'] = ['21', 0]
        with self.assertRaises(ValueError): bindings(graph)


if __name__ == '__main__': unittest.main()
