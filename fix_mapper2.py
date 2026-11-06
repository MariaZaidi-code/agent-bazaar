content = open('app/agents/mapper_stub.py', 'r').read()

# Add mapper prompt tuning methods before reset
mapper_prompt_code = '''    def get_mapper_prompt(self, tool_spec):
        """Generate a prompt for the LLM Mapper based on tool spec."""
        inputs_desc = ', '.join([f'{item.name}: {item.concept}' for item in tool_spec.inputs])
        outputs_desc = ', '.join([f'{item.name}: {item.concept}' for item in tool_spec.outputs])
        return f'''Map the following tool to ontology concepts:

Tool: {{tool_spec.name}}
Capability: {{tool_spec.capability}}
Description: {{tool_spec.description}}
Inputs: {inputs_desc}
Outputs: {outputs_desc}

Map each input and output to the most appropriate ontology concept.
Return JSON with mappings for each input and output field.'''
        return prompt

    def tune_prompt(self, feedback):
        """Store prompt tuning feedback for future improvements."""
        if not hasattr(self, '_prompt_feedback'):
            self._prompt_feedback = []
        self._prompt_feedback.append(feedback)

'''

content = content.replace(
    '    def reset(self) -> None:\n        self.corrections.clear()\n        self.listings.clear()',
    mapper_prompt_code + '    def reset(self) -> None:\n        self.corrections.clear()\n        self.listings.clear()'
)

open('app/agents/mapper_stub.py', 'w').write(content)
print('Mapper prompt tuning added')